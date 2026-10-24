"""Event model and non-blocking, retrying PostgreSQL sink.

The GStreamer probe calls ``EventSink.submit`` which never blocks: events go to a
bounded queue and a worker thread batches them into PostgreSQL. On DB failure the
worker retries with exponential back-off; events that still cannot be written are
appended to a JSONL spool file so nothing is silently lost.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional

log = logging.getLogger("vds.events")


@dataclass
class CrossingEvent:
    stream_id: str
    pipeline_run_id: str
    vehicle_id: int
    vehicle_class: str
    direction: str
    event_time: datetime
    line_id: str = "line-1"
    class_confidence: Optional[float] = None
    color: Optional[str] = None
    color_confidence: Optional[float] = None
    frame_number: Optional[int] = None
    bbox: Optional[tuple] = None  # (left, top, width, height)
    source: str = "deepstream"

    def to_row(self) -> dict:
        b = self.bbox or (None, None, None, None)
        return dict(
            stream_id=self.stream_id, pipeline_run_id=self.pipeline_run_id,
            vehicle_id=self.vehicle_id, vehicle_class=self.vehicle_class,
            class_confidence=self.class_confidence, color=self.color,
            color_confidence=self.color_confidence, direction=self.direction,
            line_id=self.line_id, event_time=self.event_time, frame_number=self.frame_number,
            bbox_left=b[0], bbox_top=b[1], bbox_width=b[2], bbox_height=b[3], source=self.source,
        )


INSERT_SQL = """
INSERT INTO crossing_events
 (stream_id, pipeline_run_id, vehicle_id, vehicle_class, class_confidence, color,
  color_confidence, direction, line_id, event_time, frame_number,
  bbox_left, bbox_top, bbox_width, bbox_height, source)
VALUES
 (%(stream_id)s, %(pipeline_run_id)s, %(vehicle_id)s, %(vehicle_class)s, %(class_confidence)s,
  %(color)s, %(color_confidence)s, %(direction)s, %(line_id)s, %(event_time)s, %(frame_number)s,
  %(bbox_left)s, %(bbox_top)s, %(bbox_width)s, %(bbox_height)s, %(source)s)
ON CONFLICT ON CONSTRAINT uq_crossing_once DO NOTHING
"""

STREAM_SQL = ("INSERT INTO streams (stream_id, rtsp_url) VALUES (%s, %s) "
              "ON CONFLICT (stream_id) DO NOTHING")

HEARTBEAT_SQL = """
INSERT INTO pipeline_heartbeats (stream_id, pipeline_run_id, state, fps, frames, last_frame_at, updated_at, detail)
VALUES (%(stream_id)s, %(run)s, %(state)s, %(fps)s, %(frames)s, %(last_frame_at)s, now(), %(detail)s)
ON CONFLICT (stream_id) DO UPDATE SET pipeline_run_id = EXCLUDED.pipeline_run_id,
  state = EXCLUDED.state, fps = EXCLUDED.fps, frames = EXCLUDED.frames,
  last_frame_at = EXCLUDED.last_frame_at, updated_at = now(), detail = EXCLUDED.detail
"""


def new_run_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventSink:
    """Asynchronous writer. ``connect`` is injectable so tests can use any DB/fake."""

    def __init__(self, dsn: str, stream_id: str, rtsp_url: str = "", run_id: Optional[str] = None,
                 max_queue: int = 1000, batch_size: int = 50, max_retries: int = 5,
                 spool_path: str = "failed_events.jsonl",
                 connect: Optional[Callable[[], object]] = None):
        self.dsn, self.stream_id, self.rtsp_url = dsn, stream_id, rtsp_url
        self.run_id = run_id or new_run_id()
        self.batch_size, self.max_retries, self.spool_path = batch_size, max_retries, spool_path
        self._q: "queue.Queue[CrossingEvent]" = queue.Queue(maxsize=max_queue)
        self._connect = connect or self._default_connect
        self._conn = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="event-sink", daemon=True)
        self._hb_lock = threading.Lock()
        self._hb: Optional[dict] = None
        self.written = 0
        self.dropped = 0
        self.spooled = 0

    # -- public API -----------------------------------------------------
    def start(self) -> None:
        self._thread.start()

    def submit(self, event: CrossingEvent) -> bool:
        """Never blocks. Returns False (and counts a drop) if the queue is full."""
        try:
            self._q.put_nowait(event)
            return True
        except queue.Full:
            self.dropped += 1
            log.error("event queue full, dropping event for track %s", event.vehicle_id)
            return False

    def set_heartbeat(self, state: str, fps: float = 0.0, frames: int = 0,
                      last_frame_at: Optional[datetime] = None, detail: str = "") -> None:
        with self._hb_lock:
            self._hb = dict(stream_id=self.stream_id, run=self.run_id, state=state, fps=fps,
                            frames=frames, last_frame_at=last_frame_at, detail=detail)

    def close(self, timeout: float = 10.0) -> None:
        """Flush pending events (bounded wait), then stop the worker and close the DB."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout)
        self._drain_to_spool()
        self._close_conn()

    # -- worker ---------------------------------------------------------
    def _default_connect(self):
        import psycopg
        return psycopg.connect(self.dsn, autocommit=False, connect_timeout=5)

    def _close_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None

    def _ensure_conn(self):
        if self._conn is None:
            self._conn = self._connect()
            with self._conn.cursor() as cur:
                cur.execute(STREAM_SQL, (self.stream_id, self.rtsp_url))
            self._conn.commit()
        return self._conn

    def _run(self) -> None:
        last_hb = 0.0
        while not (self._stop.is_set() and self._q.empty()):
            batch: List[CrossingEvent] = []
            try:
                batch.append(self._q.get(timeout=0.5))
                while len(batch) < self.batch_size:
                    batch.append(self._q.get_nowait())
            except queue.Empty:
                pass
            if batch:
                self._write_with_retry(batch)
            if time.monotonic() - last_hb >= 2.0:
                last_hb = time.monotonic()
                self._write_heartbeat()

    def _write_with_retry(self, batch: List[CrossingEvent]) -> None:
        delay = 0.5
        for attempt in range(1, self.max_retries + 1):
            try:
                conn = self._ensure_conn()
                with conn.cursor() as cur:
                    cur.executemany(INSERT_SQL, [e.to_row() for e in batch])
                conn.commit()
                self.written += len(batch)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("DB write failed (attempt %d/%d): %s", attempt, self.max_retries, exc)
                self._close_conn()
                if self._stop.is_set() and attempt >= 2:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
        self._spool(batch)

    def _write_heartbeat(self) -> None:
        with self._hb_lock:
            hb = dict(self._hb) if self._hb else None
        if not hb:
            return
        try:
            conn = self._ensure_conn()
            with conn.cursor() as cur:
                cur.execute(HEARTBEAT_SQL, hb)
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("heartbeat write failed: %s", exc)
            self._close_conn()

    def _spool(self, batch: List[CrossingEvent]) -> None:
        try:
            with open(self.spool_path, "a", encoding="utf-8") as f:
                for e in batch:
                    d = asdict(e)
                    d["event_time"] = e.event_time.isoformat()
                    f.write(json.dumps(d) + "\n")
            self.spooled += len(batch)
            log.error("spooled %d events to %s", len(batch), self.spool_path)
        except OSError as exc:
            self.dropped += len(batch)
            log.error("could not spool events: %s", exc)

    def _drain_to_spool(self) -> None:
        rest: List[CrossingEvent] = []
        while True:
            try:
                rest.append(self._q.get_nowait())
            except queue.Empty:
                break
        if rest:
            self._spool(rest)
