# Task ledger

Status: COMPLETE = implemented **and** verified by execution · PARTIAL · BLOCKED · NOT STARTED.
Dev machine: Windows 11, Intel Core 5 210H, 15.6 GB RAM, RTX 3050 A Laptop 4 GB (driver 572.40).
No Docker, no WSL, no PostgreSQL, no system FFmpeg at inspection time (FFmpeg 7.1 obtained via the `imageio-ffmpeg` pip wheel).

| # | Requirement | Status | Evidence / notes |
|---|---|---|---|
| 1 | MediaMTX config + RTSP publishing scripts | PARTIAL | Verified 2026-10-23 on Windows: MediaMTX v1.21.2 with `mediamtx/mediamtx.yml`; FFmpeg 7.1 published a **synthetic `testsrc` pattern (not traffic footage)**; API showed path `traffic` ready with H264; an independent FFmpeg RTSP client decoded 50 frames. Not verified: real traffic video, VLC, `publish_video.*` scripts' loop/retry, HLS. |
| 2 | DeepStream pipeline (nvurisrcbin→nvstreammux→PGIE→nvtracker→SGIE→probe) | BLOCKED | Code + configs written (`deepstream/`). DeepStream is Linux-only; this machine has no WSL/Docker/Linux. Never executed: **no claim is made that it runs**. |
| 3 | Primary detector | BLOCKED | `config_infer_primary.txt` targets DS sample `Primary_Detector`; model file names unverified against a real container (`scripts/prepare_models.sh` checks them). |
| 4 | Tracker (NvDCF) | BLOCKED | `tracker_NvDCF.yml` written; untested. |
| 5 | Secondary colour classifier | BLOCKED | `config_infer_secondary_color.txt` (DS sample `Secondary_CarColor`, 12 colours); untested. Accuracy unmeasured. |
| 6 | Line-crossing logic (dedupe, direction, hysteresis, eviction) | COMPLETE (logic only) | `deepstream/tests/test_crossing.py`, 11 tests pass. Synthetic coordinates; does not prove real-video accuracy. |
| 7 | Async DB sink (queue, retry, spool, idempotent) | COMPLETE | 4 sink tests pass incl. real PostgreSQL 16.4 duplicate-insert test (1 row for 2 identical submits). |
| 8 | PostgreSQL schema | COMPLETE | Applied to PostgreSQL 16.4 (portable build); constraints exercised by tests. |
| 9 | FastAPI backend (6 required endpoints + timeseries + SSE) | COMPLETE | 8 API tests pass vs real Postgres (totals, filters, pagination, validation, injection, 503 when DB down). SSE stream used by the dashboard successfully; no dedicated SSE unit test. |
| 10 | React dashboard | COMPLETE (with test data) | Build OK, 4 vitest pass. Rendered in browser against live API: counters/colour/class/table/status populated; total went 6→8 without reload after 2 new events. Events were `source='test'` rows from `scripts/dev_emit_test_events.py`, **not DeepStream detections**. |
| 11 | End-to-end run (RTSP→DS→DB→API→UI) | BLOCKED | Needs a DeepStream host. |
| 12 | Metrics (FPS, accuracy, latency) | NOT STARTED | Nothing measured; see `docs/testing.md` for how to measure. |
| 13 | README / docs | PARTIAL | Written; kept in sync with the statuses here. |
| 14 | Walkthrough script | COMPLETE | `docs/walkthrough.md`. The recording itself (camera on) must be done by the candidate. |
| 15 | Git repo / GitHub | PARTIAL | Local git repo only. No GitHub repo created (no authenticated access; assignment is confidential - publish privately). |

## Blockers
**DeepStream runtime** - Evidence: `wsl` reports the subsystem is not installed; `docker` not found; DeepStream has no Windows build.
Done: all code/config. Unverified: everything that touches GStreamer/TensorRT.
Smallest unblock: run on a Linux+NVIDIA box, or enable WSL2 + Docker Desktop (needs admin rights/reboot) and `docker compose --profile gpu up`.
