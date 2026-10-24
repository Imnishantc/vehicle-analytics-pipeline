# Testing and validation status

## Commands
```bash
python -m pip install -r backend/requirements.txt pytest httpx pyyaml
python -m pytest deepstream/tests backend/tests -q          # DB tests skip without TEST_DATABASE_URL
TEST_DATABASE_URL=postgresql://user:pw@localhost:5432/vehicles_test python -m pytest -q   # use a THROWAWAY database
cd frontend && npm install && npm test && npm run build
```
Tests insert rows with `source='test'`/`stream_id='cam-apitest'` and delete them afterwards.

## What each suite proves
| Suite | Proves | Does NOT prove |
|---|---|---|
| `deepstream/tests/test_crossing.py` | direction, dedupe, hysteresis, occlusion, eviction on synthetic coordinates | real-video counting accuracy |
| `deepstream/tests/test_event_sink.py` | non-blocking submit, batching, retry→spool; (with Postgres) idempotent insert | pyds metadata extraction |
| `backend/tests/test_api.py` | endpoint results vs. real PostgreSQL, filters, validation, SQL-injection inertness, 503 when DB is down | - |
| `frontend/src/format.test.js` | helper functions | rendering (build verified only) |

## Not yet validated (needs a DeepStream host)
Pipeline element linking, nvinfer engine build with the sample models, NvDCF ID persistence, colour predictions,
reconnect behaviour, FPS. See `docs/LEDGER.md` for the live status of each.

## How to measure the unmeasured metrics
- **FPS**: pipeline writes `fps` to `pipeline_heartbeats` every 2 s (`select * from pipeline_heartbeats`).
- **Counting accuracy**: watch a clip, manually count crossings per direction, compare to `select direction,count(*) ... where stream_id=...`.
- **Colour accuracy**: crop vehicles from the clip, hand-label, compare to `crossing_events.color`.
- **Latency**: compare `event_time` with `created_at` (DB insertion time).
No numbers are reported here because none have been measured.
