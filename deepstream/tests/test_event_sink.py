"""EventSink tests. Queue/retry/spool behaviour uses a fake connection; the DB test
needs a real PostgreSQL (TEST_DATABASE_URL) and is skipped otherwise."""
import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deepstream" / "src"))
from vds.events import CrossingEvent, EventSink  # noqa: E402


def ev(vid=1, direction="in", run="00000000-0000-0000-0000-000000000001"):
    return CrossingEvent("cam-t", run, vid, "Car", direction, datetime.now(timezone.utc),
                         color="red", color_confidence=0.9, source="test", bbox=(1, 2, 3, 4))


class FakeCur:
    def __init__(self, conn): self.c = conn
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None): self.c.log.append(("exec", params))
    def executemany(self, sql, rows):
        if self.c.fail:
            raise RuntimeError("db down")
        self.c.rows.extend(rows)


class FakeConn:
    def __init__(self, fail=False): self.fail, self.rows, self.log = fail, [], []
    def cursor(self): return FakeCur(self)
    def commit(self): pass
    def close(self): pass


def test_submit_never_blocks_and_counts_drops(tmp_path):
    s = EventSink("x", "cam-t", max_queue=2, spool_path=str(tmp_path / "s.jsonl"), connect=lambda: FakeConn())
    t0 = time.monotonic()
    results = [s.submit(ev(i)) for i in range(5)]  # worker not started -> queue fills
    assert time.monotonic() - t0 < 0.5
    assert results == [True, True, False, False, False] and s.dropped == 3


def test_events_written_in_batches(tmp_path):
    conn = FakeConn()
    s = EventSink("x", "cam-t", spool_path=str(tmp_path / "s.jsonl"), connect=lambda: conn)
    s.start()
    for i in range(10):
        s.submit(ev(i))
    s.close()
    assert len(conn.rows) == 10 and s.written == 10 and s.spooled == 0


def test_persistent_failure_spools_to_disk(tmp_path):
    spool = tmp_path / "s.jsonl"
    s = EventSink("x", "cam-t", max_retries=2, spool_path=str(spool), connect=lambda: FakeConn(fail=True))
    s.start()
    s.submit(ev(5))
    deadline = time.monotonic() + 15
    while s.spooled == 0 and time.monotonic() < deadline:
        time.sleep(0.1)
    s.close(timeout=5)
    lines = [json.loads(l) for l in spool.read_text().splitlines()]
    assert len(lines) == 1 and lines[0]["vehicle_id"] == 5


DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set (needs real PostgreSQL)")
def test_real_postgres_idempotent_insert(tmp_path):
    import psycopg
    with psycopg.connect(DSN) as c:
        c.execute((ROOT / "database" / "schema.sql").read_text())
        c.execute("DELETE FROM crossing_events WHERE stream_id='cam-sinktest'")
        c.commit()
    s = EventSink(DSN, "cam-sinktest", spool_path=str(tmp_path / "s.jsonl"))
    s.start()
    e = ev(42)
    e.stream_id = "cam-sinktest"
    s.submit(e)
    s.submit(e)  # duplicate must be ignored by the unique constraint
    s.close()
    with psycopg.connect(DSN) as c:
        n = c.execute("SELECT count(*) FROM crossing_events WHERE stream_id='cam-sinktest'").fetchone()[0]
    assert n == 1
