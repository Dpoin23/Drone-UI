"""A running processing session: frame source -> latest-frame buffer -> workers -> aggregation.

One session per account (the operator's detections are logged to their account), with a global
cap because every session loads its own models: ByteTrack state can't be shared between streams.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

from ..config import Settings
from .aggregate import DetectionAggregator, IssueSink, iso
from .detectors import Detector, load_crop_classifier, load_detector
from .frames import LatestFrameBuffer
from .hub import EventHub
from .modes import STREAMS, FlightMode, Stream, mode_from_telemetry
from .sources import BrowserFrame, BrowserSource, CaptureTarget, ServerCapture
from .telemetry import Telemetry, TelemetryState
from .workers import InferenceWorker

log = logging.getLogger(__name__)

FrameSource = Literal["server", "browser"]
DetectorFactory = Callable[[Stream, Settings], Detector]

MAX_PUSH_FPS = 15.0


@dataclass(frozen=True)
class SessionConfig:
    mode: FlightMode
    rates: dict[FlightMode, dict[Stream, float]]
    auto_issues: bool
    follow_telemetry: bool
    frame_source: FrameSource
    transport: str
    source_label: str
    capture: CaptureTarget | None = None
    video_title: str | None = None

    def source_key(self) -> tuple:
        return (self.frame_source, self.transport, self.capture)


class VisionSession:
    def __init__(self, user_id: int, config: SessionConfig, *, settings: Settings, hub: EventHub,
                 telemetry: TelemetryState, detector_factory: DetectorFactory) -> None:
        self.user_id = user_id
        self.settings = settings
        self.hub = hub
        self.telemetry = telemetry
        self.started_at = time.time()
        self._config = config
        self._config_lock = threading.Lock()
        self.buffer = LatestFrameBuffer()
        self.browser = BrowserSource(self.buffer)
        self.capture: ServerCapture | None = None
        self.source_state = "waiting"
        self.source_message: str | None = None
        self._fps_sample: tuple[float, int] | None = None
        self._fps_value = 0.0

        crop_classifier = None
        try:
            crop_classifier = load_crop_classifier(settings)
        except Exception as exc:
            log.warning("defect classifier unavailable: %s", exc)
        self.aggregator = DetectionAggregator(
            publish=hub.publish,
            telemetry=telemetry,
            issue_sink=IssueSink(settings.db_path, settings.uploads_dir, user_id),
            context=self._context,
            crop_classifier=crop_classifier,
        )
        self.workers = {
            stream: InferenceWorker(
                stream,
                self.buffer,
                load=lambda s=stream: detector_factory(s, settings),
                rate=lambda s=stream: self.target_fps(s),
                on_result=self._on_result,
                on_reset=self.aggregator.reset,
                on_state=self.publish_status,
            )
            for stream in STREAMS
        }

    # ---- lifecycle ----

    def start(self) -> None:
        for worker in self.workers.values():
            worker.start()
        self._start_source()

    def stop(self) -> None:
        if self.capture:
            self.capture.stop()
        for worker in self.workers.values():
            worker.stop()
        self.buffer.close()

    def join(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        for worker in self.workers.values():
            worker.join(max(0.0, deadline - time.monotonic()))
        if self.capture:
            self.capture.join(max(0.0, deadline - time.monotonic()))

    def _start_source(self) -> None:
        cfg = self.config
        if cfg.frame_source == "server" and cfg.capture is not None:
            self.capture = ServerCapture(cfg.capture, self.buffer, self._on_source_status)
            self.capture.start()
        else:
            self._on_source_status("waiting", "Waiting for frames from the browser")

    # ---- config ----

    @property
    def config(self) -> SessionConfig:
        with self._config_lock:
            return self._config

    def update(self, config: SessionConfig) -> bool:
        """Apply new settings. Returns False if the frame source changed and a restart is needed."""
        with self._config_lock:
            if config.source_key() != self._config.source_key():
                return False
            self._config = config
        for worker in self.workers.values():
            worker.wake()
        self.publish_status()
        return True

    def set_mode(self, mode: FlightMode) -> None:
        with self._config_lock:
            if self._config.mode == mode:
                return
            self._config = replace(self._config, mode=mode)
        for worker in self.workers.values():
            worker.wake()
        self.publish_status()

    def on_telemetry(self, telemetry: Telemetry) -> None:
        mode = mode_from_telemetry(telemetry.flight_mode)
        if mode and self.config.follow_telemetry:
            self.set_mode(mode)

    def target_fps(self, stream: Stream) -> float:
        cfg = self.config
        return cfg.rates[cfg.mode][stream]

    def push_fps(self) -> float:
        """How often the browser should send frames: a little above the fastest active worker."""
        active = [self.target_fps(s) for s in STREAMS if self.workers[s].state not in ("unavailable",)]
        fastest = max(active, default=0.0)
        return 0.0 if fastest <= 0 else min(MAX_PUSH_FPS, fastest + 2)

    def _context(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "mode": cfg.mode,
            "auto_issues": cfg.auto_issues,
            "video_title": cfg.video_title,
            "source_label": cfg.source_label,
        }

    # ---- frames and results ----

    def push_browser_frame(self, producer_id: str, frame: BrowserFrame) -> bool:
        if self.config.frame_source != "browser":
            return False
        accepted = self.browser.push(producer_id, frame)
        if accepted and self.source_state != "live":
            self._on_source_status("live", None)
        return accepted

    def release_producer(self, producer_id: str) -> None:
        self.browser.release(producer_id)

    def _on_source_status(self, state: str, message: str | None) -> None:
        self.source_state, self.source_message = state, message
        self.publish_status()

    def _on_result(self, stream: Stream, frame, detections, detector: str, infer_ms: float) -> None:
        self.aggregator.handle(stream, frame, detections, detector=detector, infer_ms=infer_ms)

    # ---- reporting ----

    def status(self) -> dict[str, Any]:
        cfg = self.config
        source_state = self.source_state
        if cfg.frame_source == "browser" and source_state == "live" and not self.browser.receiving:
            source_state = "waiting"
        return {
            "running": True,
            "started_at": iso(self.started_at),
            "mode": cfg.mode,
            "rates": cfg.rates,
            "auto_issues": cfg.auto_issues,
            "follow_telemetry": cfg.follow_telemetry,
            "frame_source": cfg.frame_source,
            "transport": cfg.transport,
            "source": {"label": cfg.source_label, "state": source_state, "message": self.source_message},
            "push_fps": self.push_fps(),
            "push_max_width": max(1280, self.settings.vision_imgsz),
            "workers": {s: w.snapshot(self.target_fps(s)) for s, w in self.workers.items()},
        }

    def stats(self) -> dict[str, Any]:
        buf = self.buffer
        elapsed = max(time.time() - self.started_at, 1e-6)
        latest = buf.latest()
        return {
            "type": "stats",
            "frames_in": buf.frames_in,
            "frames_overwritten": buf.overwritten,
            "capture_fps": round(self._capture_fps(), 2),
            "ingest_kbps": round(buf.bytes_in * 8 / 1000 / elapsed, 1) if buf.bytes_in else None,
            "frame_size": [latest.width, latest.height] if latest else None,
            "alerts": self.aggregator.alerts,
            "issues_created": self.aggregator.issues_created,
            "telemetry": self.telemetry.snapshot(),
            "workers": {s: w.snapshot(self.target_fps(s)) for s, w in self.workers.items()},
        }

    def _capture_fps(self) -> float:
        now, count = time.monotonic(), self.buffer.frames_in
        if self._fps_sample is not None:
            then, before = self._fps_sample
            if now - then >= 0.5:
                self._fps_value = (count - before) / (now - then)
                self._fps_sample = (now, count)
        else:
            self._fps_sample = (now, count)
        return self._fps_value

    def publish_status(self) -> None:
        self.hub.publish({"type": "status", "session": self.status()})


class TooManySessions(RuntimeError):
    pass


class VisionManager:
    def __init__(self, settings: Settings, detector_factory: DetectorFactory = load_detector) -> None:
        self.settings = settings
        self.detector_factory = detector_factory
        self._lock = threading.Lock()
        self._sessions: dict[int, VisionSession] = {}
        self._hubs: dict[int, EventHub] = {}
        self._telemetry: dict[int, TelemetryState] = {}

    def hub(self, user_id: int) -> EventHub:
        with self._lock:
            return self._hubs.setdefault(user_id, EventHub())

    def telemetry(self, user_id: int) -> TelemetryState:
        with self._lock:
            return self._telemetry.setdefault(user_id, TelemetryState())

    def get(self, user_id: int) -> VisionSession | None:
        with self._lock:
            return self._sessions.get(user_id)

    def start(self, user_id: int, config: SessionConfig) -> VisionSession:
        self.stop(user_id)
        hub, telemetry = self.hub(user_id), self.telemetry(user_id)
        session = VisionSession(user_id, config, settings=self.settings, hub=hub, telemetry=telemetry,
                                detector_factory=self.detector_factory)
        with self._lock:
            if user_id in self._sessions or len(self._sessions) >= self.settings.vision_max_sessions:
                raise TooManySessions(
                    f"The ground station is already running {len(self._sessions)} processing session(s)"
                )
            self._sessions[user_id] = session
        session.start()
        session.publish_status()
        return session

    def apply(self, user_id: int, config: SessionConfig) -> VisionSession | None:
        """Push new settings into a running session, restarting it if the frame source changed."""
        session = self.get(user_id)
        if session is None:
            return None
        if session.update(config):
            return session
        return self.start(user_id, config)

    def stop(self, user_id: int) -> bool:
        with self._lock:
            session = self._sessions.pop(user_id, None)
        if session is None:
            return False
        session.stop()
        session.join()
        self.hub(user_id).publish({"type": "status", "session": {"running": False}})
        return True

    def update_telemetry(self, user_id: int, telemetry: Telemetry) -> None:
        self.telemetry(user_id).update(telemetry)
        session = self.get(user_id)
        if session:
            session.on_telemetry(telemetry)

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.stop()
        for session in sessions:
            session.join(2.0)
