"""Flight modes and how fast each detector runs in them.

The defaults are the plan's initial targets. They are per account and editable from the UI,
since the right rates depend on the laptop's hardware and the flight conditions.
"""

from typing import Literal

FlightMode = Literal["takeoff_landing", "transit", "patrol", "inspection", "return_to_base"]
Stream = Literal["intruder", "maintenance"]

FLIGHT_MODES: tuple[FlightMode, ...] = ("takeoff_landing", "transit", "patrol", "inspection", "return_to_base")
STREAMS: tuple[Stream, ...] = ("intruder", "maintenance")

MODE_LABELS: dict[FlightMode, str] = {
    "takeoff_landing": "Takeoff / landing",
    "transit": "Transit",
    "patrol": "Perimeter patrol",
    "inspection": "Infrastructure inspection",
    "return_to_base": "Return to base",
}

# Inference rates in frames per second. 0 turns the detector off.
DEFAULT_RATES: dict[FlightMode, dict[Stream, float]] = {
    "takeoff_landing": {"intruder": 0, "maintenance": 0},
    "transit": {"intruder": 8, "maintenance": 0},
    "patrol": {"intruder": 8, "maintenance": 0},
    "inspection": {"intruder": 3, "maintenance": 1.5},
    # Intruder detection is optional on the way home; raise it here to keep watching.
    "return_to_base": {"intruder": 0, "maintenance": 0},
}

MAX_RATE = 30.0

# Flight-mode names the drone may report in telemetry, mapped to processing modes.
_TELEMETRY_ALIASES: dict[str, FlightMode] = {
    "takeoff": "takeoff_landing",
    "landing": "takeoff_landing",
    "land": "takeoff_landing",
    "takeoff_landing": "takeoff_landing",
    "transit": "transit",
    "mission": "transit",
    "auto": "transit",
    "patrol": "patrol",
    "perimeter_patrol": "patrol",
    "inspection": "inspection",
    "inspect": "inspection",
    "infrastructure_inspection": "inspection",
    "rtl": "return_to_base",
    "rtb": "return_to_base",
    "return": "return_to_base",
    "return_to_base": "return_to_base",
    "return_to_launch": "return_to_base",
}


def mode_from_telemetry(name: str | None) -> FlightMode | None:
    if not name:
        return None
    return _TELEMETRY_ALIASES.get(name.strip().lower().replace(" ", "_").replace("-", "_"))


def merged_rates(overrides: dict | None) -> dict[FlightMode, dict[Stream, float]]:
    """Defaults with any valid per-account overrides applied."""
    rates = {mode: dict(streams) for mode, streams in DEFAULT_RATES.items()}
    for mode, streams in (overrides or {}).items():
        if mode not in rates or not isinstance(streams, dict):
            continue
        for stream, fps in streams.items():
            if stream in STREAMS and isinstance(fps, int | float):
                rates[mode][stream] = min(max(float(fps), 0.0), MAX_RATE)
    return rates
