# Drone-UI

Ground-station UI for the perimeter-surveillance drone. Operators sign in, watch the drone's live feed, and log security risks and maintenance issues. Everything an operator logs is stored with their account, so it persists across sessions and devices.

See [docs/DESIGN_PLAN.md](docs/DESIGN_PLAN.md) for the full architecture, and [docs/VISION_PIPELINE.md](docs/VISION_PIPELINE.md) for the image processing.

## What's here

| Path | What it is |
|---|---|
| `ground-station/` | Python / FastAPI backend. Accounts, sign-in tokens, and per-account storage in SQLite. Ground-side image processing (YOLO + ByteTrack) in `app/vision/`, with training and benchmark tools in `tools/`. |
| `web/` | React + TypeScript + Vite + Tailwind frontend (dark theme). |
| `scripts/dev.sh` | Starts both for local development. |
| `scripts/train-models.sh` | Trains the vision models end to end on a local NVIDIA GPU and publishes them as a GitHub Release (see [docs/TRAINING.md](docs/TRAINING.md)). |
| `scripts/fetch-models.sh` | Installs the newest published model weights into `ground-station/models/`. |

The signed-in app has three tabs:

- **Livestream**: video panel with a built-in **demo feed** (no drone needed), plus WebRTC (WHEP, for MediaMTX on the Pi) and MJPEG options. Stream settings are saved per account. Quick buttons log a security risk or maintenance issue straight from the feed, with a snapshot of the current frame attached, and a sidebar shows active issues.
- **Test video** (a Livestream transport): plays recorded footage through the same feed display, so image processing can be tested without the drone. Under **Stream settings → Test video**, paste a YouTube link (or a link from most other video sites), or upload a file (MP4, MOV, WebM, MKV, Ogg). Links are downloaded to the ground station in the background. The player has play/pause, stop, ±10 s, frame-by-frame stepping, seeking, speed, loop, and mute. Keyboard shortcuts work once the player has focus: Space/K play/pause, J/L ±10 s, ←/→ ±5 s, `,`/`.` previous/next frame, Home stop, M mute.
- **Image processing** (Livestream sidebar): runs intruder detection (people and vehicles, tracked with ByteTrack) and maintenance detection (building defects) on whatever the feed is showing, at rates set by the flight mode. Boxes are drawn over the video, and confirmed detections pop up as alerts and are logged as issues automatically. See [Image processing](#image-processing).
- **Security risks** and **Maintenance**: log, search, filter, and sort issues. Each entry can have images (JPEG, PNG, GIF, or WebP, up to 10 MB each), and the list previews the first one. Click an entry to change its status (open, acknowledged / in progress, resolved, false positive / dismissed), edit its severity, location, or notes, add or remove images, or delete it.

### Automated issue creation

While image processing runs, each confirmed detection is logged as a security risk or maintenance issue with an annotated snapshot, time, GPS position (if telemetry is posted), detector, and track. The pipeline calls `insert_issue` and `save_image` in `ground-station/app/storage/issues.py`, the same functions the API uses, with `source = "ground"`, and the UI tags those entries as **Auto**. Manual entry stays available alongside it. A future on-board detector on the Pi would do the same with `source = "onboard"`.

## Prerequisites

- Python 3.11+
- Node.js 20+ and npm

## Local setup (one time)

```bash
# Backend
cd ground-station
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cd ..

# Frontend
cd web
npm ci
cd ..
```

On Debian/Ubuntu, if `python3 -m venv` fails, install `python3-venv` first (`sudo apt install python3-venv`).

Importing from YouTube uses [yt-dlp](https://github.com/yt-dlp/yt-dlp), which is in `requirements.txt` (rerun the `pip install` line after pulling). yt-dlp needs a JavaScript runtime for YouTube. The Node.js you already have works, and so do Deno and Bun. **ffmpeg is optional:**

- Without ffmpeg, YouTube imports are video-only (no sound), up to 1080p. That's all the image processing needs.
- With ffmpeg (`sudo apt install ffmpeg`), video and audio are merged into one MP4.

Image processing is optional and needs a few more packages (PyTorch, Ultralytics, OpenCV). On a laptop without an NVIDIA GPU, install the CPU build of PyTorch first. It's much smaller.

```bash
cd ground-station
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # no NVIDIA GPU
.venv/bin/pip install -r requirements-vision.txt
```

## Run it (development)

Start both servers with one command:

```bash
./scripts/dev.sh
```

Or run them in two terminals:

```bash
# Terminal 1: API on http://127.0.0.1:8000
cd ground-station
.venv/bin/uvicorn app.main:app --reload --reload-dir app --port 8000

# Terminal 2: UI on http://localhost:5173 (proxies /api to port 8000)
cd web
npm run dev
```

Open http://localhost:5173, click **Create account**, and pick a username and a password of at least 8 characters. You land on the Livestream tab with the demo feed running.

Interactive API docs are at http://127.0.0.1:8000/docs.

## Run it (single server, like a deployment)

Build the UI once, and the backend serves it alongside the API on one port:

```bash
cd web && npm run build && cd ..
cd ground-station
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000. Use `--host 0.0.0.0` only on a trusted LAN, such as the drone's Wi-Fi. The design plan says the ground station should never be exposed to the internet.

## Image processing

On the **Livestream** tab, pick a **Flight mode** in the **Image processing** panel and click **Start**. The two detectors run at their own rates on the newest frame, never a queued backlog:

| Flight mode | Intruder detection | Maintenance detection |
|---|---|---|
| Takeoff / landing | Off | Off |
| Transit | 8 FPS | Off |
| Perimeter patrol | 8 FPS | Off |
| Infrastructure inspection | 3 FPS | 1.5 FPS |
| Return to base | Off (optional) | Off |

The rates are starting targets. Edit them under **Processing settings** to suit the laptop. The panel shows each detector's actual FPS, inference time, and skipped frames. Processing works with every feed type: the ground station decodes WebRTC (through MediaMTX's RTSP port) and MJPEG streams itself, and the browser sends frames for the demo feed and test videos, so detections follow pause, seek, and frame stepping.

Models: intruder detection starts with the stock COCO `yolov8n.pt`, downloaded on first use. Maintenance detection needs weights trained on MBDD2025. `tools/train.py` trains both (VisDrone and MBDD2025), `scripts/train-models.sh` runs the whole training path on a local NVIDIA GPU and publishes the weights, `scripts/fetch-models.sh` installs the published weights, and `tools/benchmark.py` measures mAP, precision, recall, FPS, and latency. To GPS-tag detections, post the drone's position to `POST /api/vision/telemetry`. [docs/VISION_PIPELINE.md](docs/VISION_PIPELINE.md) covers the architecture, training, benchmarking, the Pi-side MediaMTX setup, and all settings.

## Testing

```bash
# Backend: lint, then API tests (auth, per-account isolation, issue CRUD, image uploads, stream settings,
# and the vision pipeline with a stand-in detector, so no PyTorch is needed)
cd ground-station
.venv/bin/ruff check .
.venv/bin/pytest

# Frontend type-check + production build, and lint
cd web
npm run build
npm run lint
```

### Manual test checklist

1. Create an account, sign out, and sign back in. A page refresh should keep you signed in.
2. On **Security risks**, log an entry with one or two images. The list should preview the first image, with a **+1** badge if there are two. Open the entry, click an image to view it full size, then mark the entry **Acknowledged** and then **Resolved**. Check that it leaves the **Active** filter.
3. On **Livestream**, use **Log from feed → Maintenance**. The form should already have a snapshot of the current frame attached. Confirm the entry appears in the sidebar and on the **Maintenance** tab.
4. Create a second account in a private window and confirm it sees none of the first account's entries.
5. Under **Stream settings**, switch to MJPEG or WebRTC with your drone or MediaMTX URL, save, and reload. The setting should persist.
6. Under **Stream settings → Test video**, import a YouTube link. It appears in the library with download progress, and you can save straight away, because the feed shows the progress and starts playing when the download is ready. Pause, step a few frames with `.`, and use **Log from feed**. The snapshot should be that exact frame. Then upload a local video file and switch to it.
7. With vision installed and a test video with people in it playing, set **Flight mode** to Perimeter patrol and click **Start**. Boxes labelled `person #<track>` follow people. Within a few seconds a "Person detected" alert pops up, and an **Auto** entry with an annotated snapshot appears under **Security risks**. Pause the video, and the boxes stay on the paused frame. Switch to Takeoff / landing, and detection stops.

### Testing against a real video stream

- **MediaMTX (WebRTC):** run [MediaMTX](https://github.com/bluenviron/mediamtx) with any source. For example, publish a webcam or test file to a path named `cam`, then set the URL to `http://<host>:8889/cam/whep`.
- **MJPEG:** any `multipart/x-mixed-replace` URL works, such as `http://drone.local:8080/stream.mjpg`.

## Configuration

Environment variables for the backend:

| Variable | Default | Purpose |
|---|---|---|
| `DRONE_UI_DB` | `ground-station/data/drone-ui.db` | SQLite file. Delete it, and the uploads folder, to reset all accounts and data. |
| `DRONE_UI_UPLOADS` | `ground-station/data/uploads` | Where issue images are stored on disk. |
| `DRONE_UI_VIDEOS` | `ground-station/data/videos` | Test-video library (uploads and imported links), one folder per account. |
| `DRONE_UI_MAX_VIDEO_MB` | `4096` | Largest test video that can be uploaded or imported. |
| `DRONE_UI_WEB_DIST` | `web/dist` | Built UI to serve in single-server mode. |
| `DRONE_UI_TOKEN_TTL_HOURS` | `168` (7 days) | How long a sign-in lasts. |
| `DRONE_UI_MODELS` | `ground-station/models` | YOLO weights. `DRONE_UI_INTRUDER_MODEL`, `DRONE_UI_MAINTENANCE_MODEL`, and `DRONE_UI_DEFECT_CLASSIFIER` pick specific files. |
| `DRONE_UI_VISION_DEVICE` | auto | Inference device: `cpu`, `0` (first NVIDIA GPU), `mps`. |
| `DRONE_UI_VISION_IMGSZ` | `640` | Inference image size. |

More image-processing settings are listed in [docs/VISION_PIPELINE.md](docs/VISION_PIPELINE.md#tuning-knobs).

For the frontend dev server, `VITE_API_TARGET` overrides where `/api` is proxied (default `http://127.0.0.1:8000`).

## Auth model (kept simple on purpose)

- Usernames and passwords are stored in SQLite. Passwords are hashed with scrypt.
- Signing in returns a random bearer token. The browser keeps it in `localStorage`, and the server stores only its SHA-256 hash, so a leaked DB doesn't leak sessions. Signing out revokes the token.
- There is no password reset, roles, or rate limiting yet.

## Not built yet

- The drone link: live telemetry and on-board detections (design plan milestone M2). Until then, GPS for detections comes from `POST /api/vision/telemetry`.
- Trained VisDrone and MBDD2025 weights. The training tools are here, but the weights need a GPU run (see [docs/TRAINING.md](docs/TRAINING.md)).
- Recording or storing the livestream.
- Live streams from YouTube and similar sites. Test video only plays recorded videos for now.
- Image thumbnails. The list currently loads full-size images for its previews.
- Map view.
