"""Inference workers: one thread per detector, each running at its own rate.

A worker sleeps until its next slot (1 / target FPS), takes the newest frame from the buffer,
and runs its detector. If inference takes longer than the slot it simply runs back to back, and
the frames that arrived in the meantime are skipped rather than queued.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

from .detectors import Detector, RawDetection
from .frames import Frame, LatestFrameBuffer
from .modes import Stream

log = logging.getLogger(__name__)

RESULT_WINDOW_S = 5.0
SEEK_JUMP_S = 3.0
WAITING_AFTER_S = 2.0

ResultFn = Callable[[Stream, Frame, list[RawDetection], str, float], None]


def _percentile(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    return round(sorted_values[min(len(sorted_values) - 1, int(p * len(sorted_values)))], 1)


class WorkerStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._done: deque[tuple[float, float, float]] = deque()
        self.processed = 0
        self.skipped = 0
        self.errors = 0

    def record(self, infer_ms: float, latency_ms: float) -> None:
        now = time.monotonic()
        with self._lock:
            self.processed += 1
            self._done.append((now, infer_ms, latency_ms))
            while self._done and now - self._done[0][0] > RESULT_WINDOW_S:
                self._done.popleft()

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            recent = [d for d in self._done if now - d[0] <= RESULT_WINDOW_S]
            fps = 0.0
            if len(recent) >= 2:
                fps = (len(recent) - 1) / max(recent[-1][0] - recent[0][0], 1e-6)
            elif recent:
                fps = 1 / RESULT_WINDOW_S
            infer = sorted(d[1] for d in recent)
            latency = sorted(d[2] for d in recent)
        return {
            "actual_fps": round(fps, 2),
            "infer_ms": _percentile(infer, 0.5),
            "infer_ms_p95": _percentile(infer, 0.95),
            "latency_ms": _percentile(latency, 0.5),
            "latency_ms_p95": _percentile(latency, 0.95),
            "processed": self.processed,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class InferenceWorker:
    def __init__(self, stream: Stream, buffer: LatestFrameBuffer, *, load: Callable[[], Detector],
                 rate: Callable[[], float], on_result: ResultFn, on_reset: Callable[[Stream], None],
                 on_state: Callable[[], None]) -> None:
        self.stream = stream
        self.buffer = buffer
        self._load = load
        self._rate = rate
        self._on_result = on_result
        self._on_reset = on_reset
        self._on_state = on_state
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.stats = WorkerStats()
        self.state = "loading"
        self.message: str | None = None
        self.detector_name: str | None = None
        self.device: str | None = None
        self._thread = threading.Thread(target=self._run, name=f"vision-{stream}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def join(self, timeout: float) -> None:
        if self._thread.is_alive():
            self._thread.join(timeout)

    def wake(self) -> None:
        """Re-read the target rate now, e.g. after the flight mode changed."""
        self._wake.set()

    def _set_state(self, state: str, message: str | None = None) -> None:
        if (state, message) != (self.state, self.message):
            self.state, self.message = state, message
            self._on_state()

    def _sleep(self, seconds: float) -> None:
        self._wake.wait(seconds)
        self._wake.clear()

    def _run(self) -> None:
        try:
            detector = self._load()
        except Exception as exc:
            log.warning("%s detector unavailable: %s", self.stream, exc)
            self._set_state("unavailable", str(exc))
            return
        self.detector_name = detector.name
        self.device = getattr(detector, "device", None)

        last_seq = 0
        last_epoch: int | None = None
        last_media: float | None = None
        next_due = 0.0
        last_frame_at = time.monotonic()
        was_off = False
        while not self._stop.is_set():
            fps = self._rate()
            if fps <= 0:
                self._set_state("off")
                was_off = True
                self._sleep(0.5)
                continue
            now = time.monotonic()
            if now < next_due:
                self._sleep(next_due - now)
                continue
            frame = self.buffer.wait_newer(last_seq, timeout=0.5)
            if frame is None:
                if self.buffer.closed:
                    break
                if time.monotonic() - last_frame_at > WAITING_AFTER_S:
                    self._set_state("waiting", "Waiting for frames")
                continue
            last_frame_at = time.monotonic()

            jumped = last_media is not None and frame.media_time is not None and (
                frame.media_time < last_media or frame.media_time - last_media > SEEK_JUMP_S
            )
            if was_off or frame.epoch != last_epoch or jumped:
                # A new source, a reconnect, a seek, or a pause in processing: old tracks are invalid.
                detector.reset()
                self._on_reset(self.stream)
                was_off = False
            elif last_seq:
                self.stats.skipped += frame.seq - last_seq - 1
            last_seq, last_epoch, last_media = frame.seq, frame.epoch, frame.media_time

            started = time.monotonic()
            next_due = started + 1 / fps
            try:
                detections = detector.detect(frame)
            except Exception as exc:
                self.stats.errors += 1
                log.exception("%s inference failed", self.stream)
                self._set_state("error", f"Inference failed: {exc}")
                continue
            infer_ms = (time.monotonic() - started) * 1000
            self.stats.record(infer_ms, (time.monotonic() - frame.received) * 1000)
            self._set_state("running")
            try:
                self._on_result(self.stream, frame, detections, detector.name, infer_ms)
            except Exception:
                log.exception("%s result handling failed", self.stream)

    def snapshot(self, target_fps: float) -> dict:
        return {
            "state": self.state,
            "message": self.message,
            "detector": self.detector_name,
            "device": self.device,
            "target_fps": target_fps,
            **self.stats.snapshot(),
        }
