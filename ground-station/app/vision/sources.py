"""Frame sources that feed the latest-frame buffer.

Two ways in, so processing works with whatever the feed is showing:

* **Ground-station capture** (``server``): the ground station decodes the stream itself with
  OpenCV (FFmpeg or GStreamer backend). Used for the drone's live stream: RTSP from MediaMTX on
  the Pi, MJPEG, or a test video read straight from disk.
* **Browser frames** (``browser``): the UI pushes the frames it is displaying over the vision
  WebSocket. Used for the demo feed and test videos (so detections follow pause, seek, and frame
  stepping), and as a fallback when the ground station can't open the stream itself.
"""

import json
import os
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from .frames import LatestFrameBuffer

CaptureKind = Literal["stream", "file", "pipeline"]
StatusFn = Callable[[str, str | None], None]

CAPTURE_SCHEMES = ("rtsp", "rtsps", "rtmp", "rtmps", "srt", "udp", "rtp", "tcp", "http", "https")
MAX_BROWSER_FRAME_BYTES = 8 * 1024 * 1024
MEDIAMTX_RTSP_PORT = 8554


@dataclass(frozen=True)
class CaptureTarget:
    kind: CaptureKind
    url: str
    """Stream URL, local file path, or GStreamer pipeline."""
    label: str
    """What to show operators. Never a local filesystem path."""


def valid_capture_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme.lower() in CAPTURE_SCHEMES and bool(parts.netloc) and not any(c in url for c in "\"'\n\r\\")


def whep_to_rtsp(url: str) -> str | None:
    """MediaMTX serves each path over WHEP and RTSP: ``http://pi:8889/cam/whep`` -> ``rtsp://pi:8554/cam``."""
    parts = urlsplit(url)
    if not parts.hostname:
        return None
    path = parts.path.rstrip("/")
    if path.endswith("/whep"):
        path = path[: -len("/whep")]
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"rtsp://{host}:{MEDIAMTX_RTSP_PORT}{path}"


def derive_capture_url(transport: str, url: str) -> str | None:
    if not url:
        return None
    if transport == "webrtc":
        return whep_to_rtsp(url)
    if transport == "mjpeg":
        return url
    return None


# ---- Ground-station capture ----------------------------------------------------------------------


def _gstreamer_available(cv2) -> bool:
    try:
        info = cv2.getBuildInformation()
    except Exception:
        return False
    for line in info.splitlines():
        if line.strip().startswith("GStreamer:"):
            return "YES" in line
    return False


def capture_backends() -> dict[str, bool]:
    try:
        import cv2
    except ImportError:
        return {"opencv": False, "gstreamer": False}
    return {"opencv": True, "gstreamer": _gstreamer_available(cv2)}


def _rtsp_pipeline(url: str) -> str:
    # Low latency: no jitter buffer, and appsink keeps only the newest decoded frame.
    return (
        f'rtspsrc location="{url}" latency=0 protocols=tcp ! decodebin ! videoconvert ! '
        "video/x-raw,format=BGR ! appsink drop=true max-buffers=1 sync=false"
    )


class ServerCapture:
    """Reads frames as fast as the source delivers them and overwrites the buffer.

    Reading continuously matters even when inference is slow: OpenCV queues decoded frames
    internally, so a reader that only grabs a frame when it needs one gets stale frames.
    """

    RETRY_MAX_S = 10.0

    def __init__(self, target: CaptureTarget, buffer: LatestFrameBuffer, on_status: StatusFn) -> None:
        self.target = target
        self.buffer = buffer
        self.on_status = on_status
        self.epoch = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="vision-capture", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float) -> None:
        if self._thread.is_alive():
            self._thread.join(timeout)

    def _open(self, cv2):
        kind, url = self.target.kind, self.target.url
        if kind == "pipeline":
            return cv2.VideoCapture(url, cv2.CAP_GSTREAMER)
        if kind == "file":
            return cv2.VideoCapture(url)
        if url.lower().startswith(("rtsp://", "rtsps://")) and _gstreamer_available(cv2):
            cap = cv2.VideoCapture(_rtsp_pipeline(url), cv2.CAP_GSTREAMER)
            if cap.isOpened():
                return cap
            cap.release()
        if url.lower().startswith(("rtsp://", "rtsps://")):
            os.environ.setdefault(
                "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0"
            )
        params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000]
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, params)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run(self) -> None:
        try:
            import cv2
        except ImportError:
            self.on_status("error", "OpenCV isn't installed. Install requirements-vision.txt.")
            return
        backoff = 1.0
        while not self._stop.is_set():
            self.on_status("connecting", f"Opening {self.target.label}")
            cap = self._open(cv2)
            if not cap.isOpened():
                cap.release()
                self.on_status("error", f"Couldn't open {self.target.label}. Retrying in {backoff:.0f} s.")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self.RETRY_MAX_S)
                continue
            backoff = 1.0
            self.epoch += 1
            self.on_status("live", None)
            self._read_loop(cv2, cap)
            cap.release()
            if not self._stop.is_set():
                self.on_status("error", f"Lost {self.target.label}. Reconnecting.")
                self._stop.wait(1.0)

    def _read_loop(self, cv2, cap) -> None:
        is_file = self.target.kind == "file"
        fps = cap.get(cv2.CAP_PROP_FPS) if is_file else 0
        frame_interval = 1.0 / fps if 1 <= fps <= 240 else 1 / 30
        next_due = time.monotonic()
        while not self._stop.is_set():
            ok, image = cap.read()
            if not ok:
                if is_file and cap.set(cv2.CAP_PROP_POS_FRAMES, 0):
                    # Loop recorded footage so a test video can run unattended.
                    self.epoch += 1
                    next_due = time.monotonic()
                    continue
                return
            media_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000 if is_file else None
            self.buffer.put(ts=time.time(), epoch=self.epoch, media_time=media_time, image=image)
            if is_file:
                # Files decode faster than real time; pace them like a live camera.
                next_due += frame_interval
                delay = next_due - time.monotonic()
                if delay > 0:
                    self._stop.wait(delay)
                else:
                    next_due = time.monotonic()


# ---- Browser frames ------------------------------------------------------------------------------


class InvalidFrame(ValueError):
    pass


@dataclass(frozen=True)
class BrowserFrame:
    jpeg: bytes
    ts: float
    media_time: float | None
    epoch: int
    width: int
    height: int


def parse_browser_frame(data: bytes) -> BrowserFrame:
    """Decode a WebSocket frame message: 4-byte big-endian header length, JSON header, then JPEG."""
    if len(data) < 4 or len(data) > MAX_BROWSER_FRAME_BYTES:
        raise InvalidFrame("Frame is empty or too large")
    (header_len,) = struct.unpack(">I", data[:4])
    if header_len > 4096 or 4 + header_len >= len(data):
        raise InvalidFrame("Bad frame header")
    try:
        header = json.loads(data[4 : 4 + header_len])
    except ValueError:
        raise InvalidFrame("Bad frame header")
    if not isinstance(header, dict):
        raise InvalidFrame("Bad frame header")
    jpeg = data[4 + header_len :]
    if not jpeg.startswith(b"\xff\xd8\xff"):
        raise InvalidFrame("Frames must be JPEG")

    def number(key: str) -> float | None:
        value = header.get(key)
        return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None

    ts_ms = number("ts")
    now = time.time()
    # Trust the browser's capture time only if its clock roughly agrees with ours.
    ts = ts_ms / 1000 if ts_ms is not None and abs(ts_ms / 1000 - now) < 5 else now
    return BrowserFrame(
        jpeg=jpeg,
        ts=ts,
        media_time=number("media_time"),
        epoch=int(number("epoch") or 0),
        width=int(number("w") or 0),
        height=int(number("h") or 0),
    )


class BrowserSource:
    """Accepts frames from one producing browser tab at a time; other tabs just watch."""

    HANDOVER_S = 2.0

    def __init__(self, buffer: LatestFrameBuffer) -> None:
        self.buffer = buffer
        self._lock = threading.Lock()
        self._producer: str | None = None
        self._producer_epoch: int | None = None
        self._last_frame = 0.0
        self.epoch = 0

    def push(self, producer_id: str, frame: BrowserFrame) -> bool:
        now = time.monotonic()
        with self._lock:
            if self._producer != producer_id:
                if self._producer is not None and now - self._last_frame < self.HANDOVER_S:
                    return False
                self._producer = producer_id
                self._producer_epoch = None
            if frame.epoch != self._producer_epoch:
                self._producer_epoch = frame.epoch
                self.epoch += 1
            self._last_frame = now
            epoch = self.epoch
        self.buffer.put(ts=frame.ts, epoch=epoch, media_time=frame.media_time, jpeg=frame.jpeg,
                        width=frame.width, height=frame.height)
        return True

    @property
    def receiving(self) -> bool:
        return self._producer is not None and time.monotonic() - self._last_frame < self.HANDOVER_S

    def release(self, producer_id: str) -> None:
        with self._lock:
            if self._producer == producer_id:
                self._producer = None


def target_label(url: str) -> str:
    """A URL with any credentials stripped, for display."""
    parts = urlsplit(url)
    if parts.password or parts.username:
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return parts._replace(netloc=host).geturl()
    return url
