# Drone-UI

Ground-station UI for the perimeter-surveillance drone. Operators sign in, watch the drone's live feed, and log security risks and maintenance issues. Everything an operator logs is stored with their account, so it persists across sessions and devices.

See [docs/DESIGN_PLAN.md](docs/DESIGN_PLAN.md) for the full architecture.

## What's here

| Path | What it is |
|---|---|
| `ground-station/` | Python / FastAPI backend. Accounts, sign-in tokens, and per-account storage in SQLite. |
| `web/` | React + TypeScript + Vite + Tailwind frontend (dark theme). |
| `scripts/dev.sh` | Starts both for local development. |

The signed-in app has three tabs:

- **Livestream**: video panel with a built-in **demo feed** (no drone needed), plus WebRTC (WHEP, for MediaMTX on the Pi) and MJPEG options. Stream settings are saved per account. Quick buttons log a security risk or maintenance issue straight from the feed, with a snapshot of the current frame attached, and a sidebar shows active issues.
- **Security risks** and **Maintenance**: log, search, filter, and sort issues. Each entry can have images (JPEG, PNG, GIF, or WebP, up to 10 MB each), and the list previews the first one. Click an entry to change its status (open, acknowledged / in progress, resolved, false positive / dismissed), edit its severity, location, or notes, add or remove images, or delete it.

### Automated issue creation (planned)

Security risks and maintenance issues are meant to be **created automatically** from livestream and drone detections. Manual entry stays available alongside it. The backend is set up for this already: the detection pipeline will call `insert_issue` and `save_image` in `ground-station/app/storage/issues.py`, the same functions the API uses, passing a `source` other than `manual` (for example `onboard` or `ground`) and attaching the detection snapshot. The UI tags those entries as **Auto**.

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

## Testing

```bash
# Backend API tests: auth, per-account isolation, issue CRUD, image uploads, stream settings
cd ground-station
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

### Testing against a real video stream

- **MediaMTX (WebRTC):** run [MediaMTX](https://github.com/bluenviron/mediamtx) with any source. For example, publish a webcam or test file to a path named `cam`, then set the URL to `http://<host>:8889/cam/whep`.
- **MJPEG:** any `multipart/x-mixed-replace` URL works, such as `http://drone.local:8080/stream.mjpg`.

## Configuration

Environment variables for the backend:

| Variable | Default | Purpose |
|---|---|---|
| `DRONE_UI_DB` | `ground-station/data/drone-ui.db` | SQLite file. Delete it, and the uploads folder, to reset all accounts and data. |
| `DRONE_UI_UPLOADS` | `ground-station/data/uploads` | Where issue images are stored on disk. |
| `DRONE_UI_WEB_DIST` | `web/dist` | Built UI to serve in single-server mode. |
| `DRONE_UI_TOKEN_TTL_HOURS` | `168` (7 days) | How long a sign-in lasts. |

For the frontend dev server, `VITE_API_TARGET` overrides where `/api` is proxied (default `http://127.0.0.1:8000`).

## Auth model (kept simple on purpose)

- Usernames and passwords are stored in SQLite. Passwords are hashed with scrypt.
- Signing in returns a random bearer token. The browser keeps it in `localStorage`, and the server stores only its SHA-256 hash, so a leaked DB doesn't leak sessions. Signing out revokes the token.
- There is no password reset, roles, or rate limiting yet.

## Not built yet

- Live telemetry, and automatic issue creation from drone detections (design plan milestone M2). See [Automated issue creation](#automated-issue-creation-planned).
- Recording or storing the livestream.
- Image thumbnails. The list currently loads full-size images for its previews.
- Map view.
