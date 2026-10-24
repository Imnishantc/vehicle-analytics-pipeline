"""API tests against a REAL PostgreSQL (TEST_DATABASE_URL). Rows are inserted with
source='test' and removed afterwards; they are fixtures, not production data."""
import os
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

DSN = os.environ.get("TEST_DATABASE_URL")
ROOT = pathlib.Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set (needs real PostgreSQL)")

if DSN:
    os.environ["DATABASE_URL"] = DSN
    import psycopg
    from fastapi.testclient import TestClient
    from app import db
    from app.main import app

RUN = "11111111-1111-1111-1111-111111111111"
S = "cam-apitest"


@pytest.fixture(scope="module")
def client():
    with psycopg.connect(DSN) as c:
        c.execute((ROOT / "database" / "schema.sql").read_text())
        c.execute("DELETE FROM crossing_events WHERE stream_id=%s", (S,))
        c.execute("DELETE FROM pipeline_heartbeats WHERE stream_id=%s", (S,))
        c.execute("INSERT INTO streams (stream_id, rtsp_url) VALUES (%s,'rtsp://x') ON CONFLICT DO NOTHING", (S,))
        now = datetime.now(timezone.utc)
        rows = [  # (vehicle_id, class, color, direction, minutes_ago)
            (1, "Car", "red", "in", 5), (2, "Car", "white", "in", 4), (3, "Car", "red", "out", 3),
            (1, "Car", "red", "out", 2), (4, "Bicycle", None, "in", 1)]
        for vid, cl, col, d, m in rows:
            c.execute("""INSERT INTO crossing_events (stream_id,pipeline_run_id,vehicle_id,vehicle_class,color,
                         direction,event_time,source) VALUES (%s,%s,%s,%s,%s,%s,%s,'test')""",
                      (S, RUN, vid, cl, col, d, now - timedelta(minutes=m)))
        c.execute("INSERT INTO pipeline_heartbeats (stream_id,state,fps,frames) VALUES (%s,'running',25,100)", (S,))
        c.commit()
    db.reset_pool()
    with TestClient(app) as tc:
        yield tc
    with psycopg.connect(DSN) as c:
        c.execute("DELETE FROM crossing_events WHERE stream_id=%s", (S,))
        c.execute("DELETE FROM pipeline_heartbeats WHERE stream_id=%s", (S,))
        c.execute("DELETE FROM streams WHERE stream_id=%s", (S,))
        c.commit()
    db.reset_pool()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "up"}


def test_summary_distinguishes_events_and_unique_vehicles(client):
    j = client.get("/api/analytics/summary", params={"stream_id": S}).json()
    assert j["total_crossings"] == 5 and j["crossings_in"] == 3 and j["crossings_out"] == 2
    assert j["unique_vehicles"] == 4  # vehicle 1 crossed twice


def test_color_and_class_breakdowns(client):
    c = client.get("/api/analytics/colors", params={"stream_id": S}).json()
    assert {i["label"]: i["count"] for i in c["items"]} == {"red": 3, "white": 1, "unknown": 1}
    k = client.get("/api/analytics/classes", params={"stream_id": S}).json()
    assert {i["label"]: i["count"] for i in k["items"]} == {"Car": 4, "Bicycle": 1}


def test_events_pagination_filter_and_order(client):
    j = client.get("/api/events", params={"stream_id": S, "limit": 2}).json()
    assert j["total"] == 5 and len(j["items"]) == 2
    times = [i["event_time"] for i in j["items"]]
    assert times == sorted(times, reverse=True) and times[0].endswith("+00:00")
    j = client.get("/api/events", params={"stream_id": S, "color": "red", "direction": "out"}).json()
    assert j["total"] == 2


def test_date_filter_and_validation(client):
    start = (datetime.now(timezone.utc) - timedelta(minutes=2, seconds=30)).isoformat()
    j = client.get("/api/events", params={"stream_id": S, "start": start}).json()
    assert j["total"] == 2
    assert client.get("/api/events", params={"limit": 0}).status_code == 422
    assert client.get("/api/events", params={"direction": "sideways"}).status_code == 422
    r = client.get("/api/events", params={"start": "2030-01-01T00:00:00Z", "end": "2020-01-01T00:00:00Z"})
    assert r.status_code == 422


def test_sql_injection_attempt_is_inert(client):
    r = client.get("/api/events", params={"stream_id": S, "color": "red'; DROP TABLE crossing_events;--"})
    assert r.status_code == 200 and r.json()["total"] == 0
    assert client.get("/api/events", params={"stream_id": S}).json()["total"] == 5


def test_streams_status_and_timeseries(client):
    items = {i["stream_id"]: i for i in client.get("/api/streams/status").json()["items"]}
    assert items[S]["state"] == "running" and items[S]["pipeline_alive"] is True
    ts = client.get("/api/analytics/timeseries", params={"bucket": "hour", "stream_id": S}).json()
    assert sum(i["count"] for i in ts["items"]) == 5


def test_database_down_returns_503_and_degraded_health():
    db.reset_pool()
    old = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = "postgresql://nobody:x@127.0.0.1:1/none"
    try:
        with TestClient(app) as tc:
            assert tc.get("/api/health").json()["status"] == "degraded"
            assert tc.get("/api/analytics/summary").status_code == 503
    finally:
        os.environ["DATABASE_URL"] = old
        db.reset_pool()
