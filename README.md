# Vehicle Analytics Pipeline

A real-time vehicle detection, line-crossing analytics, and dashboard project built with NVIDIA DeepStream, MediaMTX, PostgreSQL, FastAPI, and React.

## Features

- Vehicle detection and tracking using NVIDIA DeepStream.
- Configurable line-crossing detection and direction labels.
- PostgreSQL event storage.
- FastAPI endpoints for summaries, vehicle classes, color breakdowns, time series, events, and stream status.
- React dashboard with live video, analytics, and event history.
- RTSP ingest and HLS playback through MediaMTX.
- Docker Compose services for the backend, frontend, database, and streaming server.
- Optional GPU-enabled DeepStream and FFmpeg publisher services.

**Current scope:** Vehicle color classification is disabled. The color chart can display stored color values, but this project does not currently classify vehicle colors in the live pipeline. Detection accuracy and throughput have not been benchmarked.

## Architecture

```text
Traffic video
    |
    v
FFmpeg publisher
    |
    v
MediaMTX (RTSP:8554)
    |
    v
NVIDIA DeepStream
    |
    +----> Annotated RTSP stream ----> MediaMTX ----> HLS dashboard playback
    |
    v
Vehicle crossing events
    |
    v
PostgreSQL
    |
    v
FastAPI
    |
    v
React dashboard
```

## Repository layout

```text
.
├── backend/                 # FastAPI application and API tests
├── database/                # PostgreSQL schema
├── deepstream/
│   ├── config/              # Pipeline, detector, and tracker configuration
│   ├── src/vds/             # DeepStream pipeline and crossing logic
│   └── tests/               # Pipeline logic tests
├── docs/                    # Testing, walkthrough, and requirement ledger
├── experiments/             # Experimental assets; not required for the main dashboard
├── frontend/                # React/Vite dashboard
├── mediamtx/                # MediaMTX configuration
├── scripts/                 # Health checks, model preparation, and publishers
├── videos/                  # Local traffic video input
├── docker-compose.yml
├── Makefile
└── README.md
```

## Prerequisites

### Basic dashboard stack

- Docker Engine or Docker Desktop with Docker Compose.
- A terminal in Linux, WSL2, or another supported Docker environment.
- A traffic video file for the optional FFmpeg publisher.

### GPU pipeline

- A compatible NVIDIA GPU and driver.
- NVIDIA Container Toolkit configured for Docker.
- Access to the NVIDIA DeepStream container image specified in `deepstream/Dockerfile`.
- The required DeepStream sample models: TrafficCamNet (`Primary_Detector`) and VehicleTypeNet (`Secondary_VehicleTypes`), as checked by `scripts/prepare_models.sh`.

The GPU profile requires a compatible NVIDIA runtime. The basic dashboard services can be run separately.

## Configuration

1. Create your local environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set a suitable PostgreSQL password. Keep `.env` private; never commit it.

3. The Compose configuration uses these environment variables:

   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`
   - `POSTGRES_DB`
   - `CORS_ORIGINS`
   - `VITE_HLS_URL` (optional frontend build argument)

4. The Compose file publishes the dashboard on port `8080`, the API on port `8000`, RTSP on port `8554`, and HLS on port `8888`. PostgreSQL is published on host port `5433`, bound to localhost.

5. Review `deepstream/config/pipeline.yml` to configure the stream ID, RTSP input, mux dimensions, counting lines, tracker, and annotated RTSP output.

## Run with Docker Compose

From the project root:

```bash
# Start database, backend, dashboard, and MediaMTX
docker compose up -d --build

# Inspect service status
docker compose ps

# Inspect logs
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 mediamtx
```

Open the dashboard:

- Dashboard: http://localhost:8080
- API documentation: http://localhost:8000/docs
- API health: http://localhost:8000/api/health
- MediaMTX HLS interface: http://localhost:8888

To run the optional FFmpeg publisher and DeepStream services:

```bash
docker compose --profile gpu up -d --build
```

The publisher reads `videos/traffic.mp4` and publishes it to `rtsp://mediamtx:8554/traffic`. Ensure the video file exists and that the GPU runtime and DeepStream models are available before starting this profile.

For an RTSP client on the host, use:

```text
rtsp://localhost:8554/traffic
```

The annotated stream is configured as:

```text
rtsp://localhost:8554/annotated
```

The dashboard's HLS URL depends on the frontend configuration and MediaMTX path setup. If needed, set `VITE_HLS_URL` in the environment used for the frontend build and rebuild the frontend.

## Stop the services

```bash
docker compose --profile gpu down
```

This stops the Compose services but preserves named volumes, including PostgreSQL data. **Do not add `-v`** unless you intentionally want to delete the named volumes and their stored data.

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | API health |
| `GET /api/analytics/summary` | Summary metrics |
| `GET /api/analytics/colors` | Stored color breakdown |
| `GET /api/analytics/classes` | Vehicle-class breakdown |
| `GET /api/analytics/timeseries` | Time-series analytics |
| `GET /api/events` | Paginated crossing events and filters |
| `GET /api/streams/status` | Stream and pipeline status |
| `GET /api/live/events` | Server-sent event stream |

See the FastAPI documentation at `/docs` for available query parameters and response formats.

## Counting configuration

The main pipeline configuration is `deepstream/config/pipeline.yml`.

It currently defines:

- Stream ID: `cam-1`.
- Input stream: `rtsp://mediamtx:8554/traffic` by default.
- Mux resolution: 1280 × 720.
- Two counting lines: `near-lane` and `far-lane`.
- Vehicle class filter: `car`.
- Color classifier: disabled.
- Annotated output: `rtsp://mediamtx:8554/annotated`.

Line coordinates are defined in muxed-frame pixels. If the video resolution or mux dimensions change, review the counting-line coordinates.

Detector and tracker settings are located in `deepstream/config/`, including the primary inference configuration and NvDCF tracker configuration.

## Testing and troubleshooting

Project test and verification notes are maintained in:

- `docs/testing.md`
- `docs/walkthrough.md`
- `docs/LEDGER.md`

Useful commands:

```bash
# Service state
docker compose ps

# Backend logs
docker compose logs --tail=100 backend

# MediaMTX logs
docker compose logs --tail=100 mediamtx

# Check the API from inside the backend container
docker compose exec -T backend python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=10).read().decode())"

# Restart only the backend if required
docker compose restart backend
```

If the dashboard does not load analytics, check the backend logs and verify the API endpoints before rebuilding containers. If the video is unavailable, check the publisher, DeepStream, MediaMTX, and HLS configuration.

The first GPU-enabled startup may take additional time while DeepStream initializes models and builds TensorRT engines.

## Security and repository hygiene

- Never commit `.env`, passwords, private keys, certificates, or other credentials.
- Use `.env.example` as a placeholder template only.
- Keep experimental model assets and generated engine files out of the repository unless explicitly needed and appropriately licensed.
- MediaMTX authentication and deployment hardening should be reviewed before exposing services beyond a trusted development environment.
- Check the license and redistribution terms for traffic videos and model files before publishing them.

## Known limitations

- Vehicle color classification is disabled in the current pipeline.
- Vehicle detection accuracy and counting accuracy have not been benchmarked.
- Throughput and latency measurements are not provided.
- Counting-line placement and direction labels may need calibration for another camera or video.
- GPU execution depends on a compatible NVIDIA driver, container runtime, DeepStream image, and model files.

