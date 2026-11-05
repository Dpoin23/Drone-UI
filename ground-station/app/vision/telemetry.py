"""Latest drone position and flight mode, used to GPS-tag detections."""

import threading
import time
from dataclasses import asdict, dataclass

# A fix older than this is not attached to a detection.
MAX_POSITION_AGE_S = 5.0


@dataclass(frozen=True)
class Telemetry:
    ts: float
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    heading_deg: float | None = None
    flight_mode: str | None = None


class TelemetryState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Telemetry | None = None

    def update(self, telemetry: Telemetry) -> None:
        with self._lock:
            self._latest = telemetry

    def latest(self) -> Telemetry | None:
        with self._lock:
            return self._latest

    def position_at(self, ts: float) -> dict | None:
        """The drone's position for a frame captured at ``ts``, if a recent enough fix exists."""
        t = self.latest()
        if t is None or t.lat is None or t.lon is None or abs(ts - t.ts) > MAX_POSITION_AGE_S:
            return None
        return {"lat": t.lat, "lon": t.lon, "alt_m": t.alt_m, "heading_deg": t.heading_deg}

    def snapshot(self) -> dict | None:
        t = self.latest()
        if t is None:
            return None
        return {**asdict(t), "age_s": round(max(0.0, time.time() - t.ts), 1)}
