# Walkthrough recording script (keep your camera ON for the entire recording)

Target length: 8-10 minutes. Do a dry run first. Have 4 windows ready: terminal, editor, browser (dashboard), DB client (psql).

## 0. Pre-flight checklist
- [ ] Camera on, microphone tested, screen share includes terminal + browser
- [ ] `docker compose --profile gpu up -d` already built once (engine build takes minutes on first run)
- [ ] `videos/traffic.mp4` present; dashboard open at http://localhost:8080; `psql` connected
- [ ] Counting line drawn at a sensible place for your video (`deepstream/config/pipeline.yml`)

## 1. Introduction (≈45 s)
Introduce yourself; goal: ingest RTSP via MediaMTX, detect/track/colour-classify vehicles with DeepStream, count line crossings, persist to PostgreSQL, show live on React.

## 2. Architecture (≈90 s) - show README Mermaid diagram
FFmpeg → MediaMTX (RTSP) → DeepStream (nvurisrcbin → nvstreammux → PGIE → nvtracker → SGIE colour → probe) → async queue → PostgreSQL → FastAPI (REST + SSE) → React.
Mention: the tracker ID is what prevents double counting; colour classifier only runs on vehicle crops.

## 3. Code walkthrough (≈3 min)
1. `deepstream/src/vds/pipeline.py` - element graph in `_build`; `_probe`/`_handle_frame`: iterate batch → frame → object meta; `rect_params` is the bounding box; `object_id` is the tracker ID; `classifier_meta_list` carries the colour.
2. `deepstream/src/vds/crossing.py` - signed distance to line, hysteresis margin, one event per (track, direction).
3. `deepstream/src/vds/events.py` - `submit()` never blocks; worker batches inserts; `ON CONFLICT DO NOTHING` on `uq_crossing_once`.
4. `database/schema.sql` - events table, unique constraint, indexes.

## 4. Live demo (≈3 min)
```bash
docker compose --profile gpu up -d
docker compose logs -f deepstream        # show engine load, FPS
curl http://localhost:9997/v3/paths/list # path "traffic" has a publisher
```
Open the RTSP URL in VLC (`rtsp://localhost:8554/traffic`) to show the stream.
```bash
docker compose exec db psql -U vehicles -c "select id,vehicle_id,color,direction,event_time from crossing_events order by id desc limit 5;"
```
Re-run it while a vehicle crosses: new rows appear. Show the dashboard counters, colour breakdown and table updating (SSE "Live" badge).
Expected: one row per vehicle per direction; counts in dashboard equal `select count(*)`.

## 5. Recovery
- No events: check the line position vs. the video; `docker compose logs deepstream`.
- Stream drops: `docker compose restart mediamtx publisher` (pipeline reconnects every 5 s).
- DB down: events are spooled to `failed_events.jsonl`; dashboard shows an error banner and recovers by itself.

## 6. Summary (≈30 s)
Recap requirements met, be upfront about anything not working or not measured (see `docs/LEDGER.md`).

> Do not claim features that you did not see working on your own machine during the dry run.
