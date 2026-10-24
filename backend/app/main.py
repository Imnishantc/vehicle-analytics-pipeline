"""FastAPI service exposing database-backed vehicle analytics.

Terminology: a *crossing event* is one row (one counted track crossing the line in
one direction). ``unique_vehicles`` counts distinct (run, stream, track) tuples, so a
vehicle that crosses in both directions yields 2 events but 1 unique vehicle.
All totals are computed from PostgreSQL; nothing is cached or synthesised.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db

STALE_AFTER_S = float(os.environ.get("HEARTBEAT_STALE_S", "10"))
Direction = Query(None, pattern="^(in|out)$")

app = FastAPI(title="Vehicle Analytics API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_methods=["GET"], allow_headers=["*"],
)


@app.exception_handler(db.DatabaseUnavailable)
async def _db_down(_req, exc):  # noqa: ANN001
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": f"database unavailable: {exc}"})


def _utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _filters(stream_id, color, vehicle_class, direction, start, end):
    if start and end and start > end:
        raise HTTPException(422, "'start' must be before 'end'")
    clauses, params = [], {}
    for col, key, val in (("stream_id", "stream_id", stream_id), ("color", "color", color),
                          ("vehicle_class", "vclass", vehicle_class), ("direction", "direction", direction)):
        if val:
            clauses.append(f"{col} = %({key})s")
            params[key] = val
    if start:
        clauses.append("event_time >= %(start)s")
        params["start"] = start
    if end:
        clauses.append("event_time < %(end)s")
        params["end"] = end
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _event_out(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": r["id"], "stream_id": r["stream_id"], "vehicle_id": r["vehicle_id"],
        "vehicle_class": r["vehicle_class"], "class_confidence": r["class_confidence"],
        "color": r["color"], "color_confidence": r["color_confidence"],
        "direction": r["direction"], "line_id": r["line_id"],
        "event_time": _utc(r["event_time"]), "frame_number": r["frame_number"],
        "bbox": None if r["bbox_left"] is None else
        {"left": r["bbox_left"], "top": r["bbox_top"], "width": r["bbox_width"], "height": r["bbox_height"]},
        "source": r["source"],
    }


@app.get("/api/health")
def health():
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "up"}
    except db.DatabaseUnavailable as exc:
        return {"status": "degraded", "database": "down", "detail": str(exc)}


@app.get("/api/analytics/summary")
def summary(stream_id: Optional[str] = None, color: Optional[str] = None,
            vehicle_class: Optional[str] = None, direction: Optional[str] = Direction,
            start: Optional[datetime] = None, end: Optional[datetime] = None):
    where, p = _filters(stream_id, color, vehicle_class, direction, start, end)
    with db.connection() as conn:
        row = conn.execute(f"""
            SELECT count(*) AS total_crossings,
                   count(*) FILTER (WHERE direction='in')  AS crossings_in,
                   count(*) FILTER (WHERE direction='out') AS crossings_out,
                   count(DISTINCT (pipeline_run_id, stream_id, vehicle_id)) AS unique_vehicles,
                   min(event_time) AS first_event, max(event_time) AS last_event
            FROM crossing_events{where}""", p).fetchone()
        last_hour = conn.execute(
            "SELECT count(*) AS n FROM crossing_events WHERE event_time >= now() - interval '1 hour'").fetchone()["n"]
    return {"total_crossings": row["total_crossings"], "crossings_in": row["crossings_in"],
            "crossings_out": row["crossings_out"], "unique_vehicles": row["unique_vehicles"],
            "crossings_last_hour": last_hour,
            "first_event": _utc(row["first_event"]), "last_event": _utc(row["last_event"])}


def _breakdown(col: str, stream_id, color, vehicle_class, direction, start, end):
    where, p = _filters(stream_id, color, vehicle_class, direction, start, end)
    with db.connection() as conn:
        label_expr = (
            "LOWER(COALESCE(vehicle_class, 'unknown'))"
            if col == "vehicle_class"
            else f"COALESCE({col}, 'unknown')"
        )
        rows = conn.execute(
            f"SELECT {label_expr} AS label, count(*) AS count "
            f"FROM crossing_events{where} GROUP BY 1 ORDER BY count DESC, label", p).fetchall()
    total = sum(r["count"] for r in rows)
    return {"total": total, "items": [dict(r) for r in rows]}


@app.get("/api/analytics/colors")
def colors(stream_id: Optional[str] = None, vehicle_class: Optional[str] = None,
           direction: Optional[str] = Direction,
           start: Optional[datetime] = None, end: Optional[datetime] = None):
    where, params = _filters(stream_id, None, vehicle_class, direction, start, end)
    if where:
        where += " AND COALESCE(source, '') != 'test'"
    else:
        where = " WHERE COALESCE(source, '') != 'test'"
    with db.connection() as conn:
        rows = conn.execute(
            f"SELECT COALESCE(color, 'unknown') AS label, count(*) AS count "
            f"FROM crossing_events{where} GROUP BY 1 ORDER BY count DESC, label",
            params,
        ).fetchall()
    total = sum(row["count"] for row in rows)
    return {"total": total, "items": [dict(row) for row in rows]}


@app.get("/api/analytics/classes")
def classes(stream_id: Optional[str] = None, color: Optional[str] = None,
            direction: Optional[str] = Direction,
            start: Optional[datetime] = None, end: Optional[datetime] = None):
    return _breakdown("vehicle_class", stream_id, color, None, direction, start, end)


@app.get("/api/analytics/timeseries")
def timeseries(bucket: str = Query("hour", pattern="^(minute|hour|day)$"),
               stream_id: Optional[str] = None, start: Optional[datetime] = None,
               end: Optional[datetime] = None):
    where, p = _filters(stream_id, None, None, None, start, end)
    with db.connection() as conn:
        rows = conn.execute(
            f"SELECT date_trunc('{bucket}', event_time) AS t, count(*) AS count "  # bucket is regex-validated
            f"FROM crossing_events{where} GROUP BY 1 ORDER BY 1", p).fetchall()
    return {"bucket": bucket, "items": [{"t": _utc(r["t"]), "count": r["count"]} for r in rows]}


@app.get("/api/events")
def events(stream_id: Optional[str] = None, color: Optional[str] = None,
           vehicle_class: Optional[str] = None, direction: Optional[str] = Direction,
           start: Optional[datetime] = None, end: Optional[datetime] = None,
           limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    where, p = _filters(stream_id, color, vehicle_class, direction, start, end)
    with db.connection() as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM crossing_events{where}", p).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM crossing_events{where} ORDER BY event_time DESC, id DESC LIMIT %(limit)s OFFSET %(offset)s",
            {**p, "limit": limit, "offset": offset}).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [_event_out(r) for r in rows]}


@app.get("/api/streams/status")
def streams_status():
    with db.connection() as conn:
        rows = conn.execute("""
            SELECT s.stream_id, s.rtsp_url, h.state, h.fps, h.frames, h.last_frame_at, h.updated_at, h.detail,
                   (SELECT max(event_time) FROM crossing_events e WHERE e.stream_id = s.stream_id) AS last_event
            FROM streams s LEFT JOIN pipeline_heartbeats h USING (stream_id) ORDER BY s.stream_id""").fetchall()
    now = datetime.now(timezone.utc)
    items: List[Dict[str, Any]] = []
    for r in rows:
        upd = r["updated_at"]
        alive = bool(upd) and (now - upd) <= timedelta(seconds=STALE_AFTER_S) and r["state"] == "running"
        state = "no_pipeline" if upd is None else (r["state"] if alive or r["state"] != "running" else "stale")
        items.append({"stream_id": r["stream_id"], "rtsp_url": r["rtsp_url"], "state": state,
                      "pipeline_alive": alive, "fps": r["fps"], "frames": r["frames"],
                      "last_frame_at": _utc(r["last_frame_at"]), "heartbeat_at": _utc(upd),
                      "last_event": _utc(r["last_event"]), "detail": r["detail"]})
    return {"items": items}


def _fetch_after(last_id: int) -> List[Dict[str, Any]]:
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM crossing_events WHERE id > %s ORDER BY id LIMIT 200", (last_id,)).fetchall()
    return [_event_out(r) for r in rows]


@app.get("/api/live/events")
async def live_events(poll_s: float = Query(1.0, ge=0.2, le=10)):
    """Server-Sent Events: pushes each newly persisted event (polls the DB)."""
    async def gen():
        try:
            with db.connection() as conn:
                last_id = conn.execute("SELECT COALESCE(max(id),0) AS m FROM crossing_events").fetchone()["m"]
        except db.DatabaseUnavailable:
            last_id = 0
        yield "retry: 3000\n\n"
        while True:
            try:
                for ev in await asyncio.to_thread(_fetch_after, last_id):
                    last_id = max(last_id, ev["id"])
                    yield f"id: {ev['id']}\nevent: crossing\ndata: {json.dumps(ev)}\n\n"
                yield ": keepalive\n\n"
            except db.DatabaseUnavailable:
                yield "event: db_down\ndata: {}\n\n"
            await asyncio.sleep(poll_s)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
