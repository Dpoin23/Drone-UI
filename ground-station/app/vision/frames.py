"""Latest-frame buffer shared by the frame source and the inference workers.

A FIFO queue would let inference fall behind the camera and report stale detections. Instead the
source overwrites a single slot, and each worker takes whatever is newest when it is ready, so
frames are skipped whenever inference can't keep up with capture.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=False)
class Frame:
    seq: int
    ts: float
    """Capture time, Unix epoch seconds."""
    received: float
    """``time.monotonic()`` when the frame reached the ground station, for latency measurement."""
    epoch: int
    """Changes whenever the source restarts, reconnects, or seeks, so trackers know to reset."""
    media_time: float | None = None
    """Position in a recorded video, in seconds. None for live streams."""
    jpeg: bytes | None = None
    width: int = 0
    height: int = 0
    _image: Any = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def image(self) -> Any:
        """Return the frame as a BGR NumPy array, decoding the JPEG once on first use."""
        with self._lock:
            if self._image is None and self.jpeg is not None:
                import cv2
                import numpy as np

                decoded = cv2.imdecode(np.frombuffer(self.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if decoded is None:
                    raise ValueError("Frame is not a decodable image")
                self._image = decoded
                self.height, self.width = decoded.shape[:2]
            return self._image


class LatestFrameBuffer:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame: Frame | None = None
        self._taken = False
        self._seq = 0
        self._closed = False
        self.frames_in = 0
        self.overwritten = 0
        """Frames replaced before any worker took them."""
        self.bytes_in = 0

    def put(self, *, ts: float, epoch: int, media_time: float | None = None, jpeg: bytes | None = None,
            image: Any = None, width: int = 0, height: int = 0) -> Frame:
        if image is not None and not (width and height):
            height, width = image.shape[:2]
        with self._cond:
            self._seq += 1
            frame = Frame(seq=self._seq, ts=ts, received=time.monotonic(), epoch=epoch, media_time=media_time,
                          jpeg=jpeg, width=width, height=height, _image=image)
            if self._frame is not None and not self._taken:
                self.overwritten += 1
            self._frame = frame
            self._taken = False
            self.frames_in += 1
            self.bytes_in += len(jpeg) if jpeg else 0
            self._cond.notify_all()
        return frame

    def latest(self) -> Frame | None:
        with self._cond:
            return self._frame

    def wait_newer(self, after_seq: int, timeout: float) -> Frame | None:
        """Block until a frame newer than ``after_seq`` is available, then return the newest one."""
        with self._cond:
            self._cond.wait_for(
                lambda: self._closed or (self._frame is not None and self._frame.seq > after_seq), timeout
            )
            if self._frame is None or self._frame.seq <= after_seq:
                return None
            self._taken = True
            return self._frame

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed
