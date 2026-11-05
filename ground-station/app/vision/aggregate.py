"""Detection aggregation: merge both streams, tag with time and GPS, and raise alerts.

Every inference result is published to the UI as a ``detections`` event. A detection becomes an
**alert** once its track is confirmed across several inference frames; alerts are logged as
issues (``source="ground"``) with an annotated snapshot, through the same storage functions the
REST API uses. Re-identified tracks of the same kind in the same place are held back by a
cooldown so one intruder doesn't fill the log.
"""

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..storage.db import connect
from ..storage.issues import InvalidImage, insert_issue, save_image
from .defects import classify_defect
from .detectors import INTRUDER_CLASSES, MAINTENANCE_MIN_CONF, CropClassifier, RawDetection
from .frames import Frame
from .modes import MODE_LABELS, Stream
from .telemetry import TelemetryState
from .tracking import IouTracker, TrackRegistry

log = logging.getLogger(__name__)

INTRUDER_REPORT_CONF = 0.3
CONFIRM_HITS: dict[Stream, int] = {"intruder": 3, "maintenance": 2}
COOLDOWN_S: dict[Stream, float] = {"intruder": 15.0, "maintenance": 60.0}
NEW_PLACE_M = 25.0
MAX_ISSUES_PER_MINUTE = 10

COLORS_BGR = {"security": (133, 113, 251), "maintenance": (36, 191, 251)}

Publish = Callable[[dict[str, Any]], None]


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _distance_m(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _clock(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds), 60)
    return f"{int(m):02d}:{s:04.1f}"


def _bbox(b: tuple[float, float, float, float]) -> dict[str, float]:
    return {"x": round(b[0], 4), "y": round(b[1], 4), "w": round(b[2], 4), "h": round(b[3], 4)}


def render_snapshot(frame: Frame, item: dict) -> bytes | None:
    """The frame as a JPEG with the detection's box drawn on it; the raw frame if that fails."""
    try:
        import cv2

        image = frame.image().copy()
        h, w = image.shape[:2]
        b = item["bbox"]
        x1, y1 = int(b["x"] * w), int(b["y"] * h)
        x2, y2 = int((b["x"] + b["w"]) * w), int((b["y"] + b["h"]) * h)
        color = COLORS_BGR[item["category"]]
        thickness = max(2, w // 480)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
        text = f"{item['label']} {item['confidence']:.2f}"
        scale = max(0.5, w / 1600)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        ty = max(th + 6, y1)
        cv2.rectangle(image, (x1, ty - th - 6), (x1 + tw + 6, ty), color, -1)
        cv2.putText(image, text, (x1 + 3, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 15, 11), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if ok:
            return buf.tobytes()
    except Exception:
        log.debug("snapshot rendering failed", exc_info=True)
    return frame.jpeg


class IssueSink:
    """Writes auto-detected issues for one account, from inference worker threads."""

    def __init__(self, db_path: Path, uploads_dir: Path, user_id: int) -> None:
        self.db_path = db_path
        self.uploads_dir = uploads_dir
        self.user_id = user_id
        self._lock = threading.Lock()

    def create(self, *, category: str, title: str, description: str, severity: str, location: str,
               snapshot: bytes | None, filename: str) -> int:
        with self._lock:
            conn = connect(self.db_path)
            try:
                issue_id = insert_issue(
                    conn, user_id=self.user_id, category=category, title=title, description=description,
                    severity=severity, location=location, source="ground",
                )
                if snapshot:
                    try:
                        save_image(conn, self.uploads_dir, user_id=self.user_id, issue_id=issue_id,
                                   data=snapshot, filename=filename)
                    except InvalidImage:
                        log.warning("detection snapshot was not a valid image")
                return issue_id
            finally:
                conn.close()


class DetectionAggregator:
    def __init__(self, *, publish: Publish, telemetry: TelemetryState, issue_sink: IssueSink | None,
                 context: Callable[[], dict[str, Any]], crop_classifier: CropClassifier | None = None) -> None:
        self.publish = publish
        self.telemetry = telemetry
        self.issue_sink = issue_sink
        self.context = context
        self.crop_classifier = crop_classifier
        self._lock = threading.Lock()
        self._intruders = TrackRegistry()
        self._defects = IouTracker()
        self._last_alert: dict[tuple[str, str], tuple[float, dict | None]] = {}
        self._issue_times: deque[float] = deque()
        self.alerts = 0
        self.issues_created = 0

    def reset(self, stream: Stream) -> None:
        with self._lock:
            (self._intruders if stream == "intruder" else self._defects).reset()

    def handle(self, stream: Stream, frame: Frame, raws: list[RawDetection], *, detector: str,
               infer_ms: float) -> dict[str, Any]:
        position = self.telemetry.position_at(frame.ts)
        if stream == "intruder":
            with self._lock:
                items, confirmed = self._intruder_items(frame, raws)
        else:
            classified = [(d, classify_defect(d, frame, self.crop_classifier))
                          for d in raws if d.confidence >= MAINTENANCE_MIN_CONF]
            with self._lock:
                items, confirmed = self._defect_items(classified)

        event = {
            "type": "detections",
            "stream": stream,
            "detector": detector,
            "frame_seq": frame.seq,
            "frame_ts": iso(frame.ts),
            "media_time": frame.media_time,
            "frame_size": [frame.width, frame.height],
            "infer_ms": round(infer_ms, 1),
            "latency_ms": round((time.monotonic() - frame.received) * 1000, 1),
            "position": position,
            "items": items,
        }
        self.publish(event)
        for item in confirmed:
            self._alert(stream, frame, item, position, detector)
        return event

    def _intruder_items(self, frame: Frame, raws: list[RawDetection]) -> tuple[list[dict], list[dict]]:
        t = frame.media_time if frame.media_time is not None else frame.ts
        items, confirmed = [], []
        for d in raws:
            if d.label not in INTRUDER_CLASSES or d.confidence < INTRUDER_REPORT_CONF:
                continue
            item: dict[str, Any] = {
                "category": "security",
                "confidence": round(d.confidence, 3),
                "bbox": _bbox(d.bbox),
            }
            if d.track_id is None:
                kind, severity = INTRUDER_CLASSES[d.label]
                items.append({**item, "id": None, "track_id": None, "label": d.label, "kind": kind,
                              "severity": severity, "velocity": None, "hits": 1})
                continue
            track = self._intruders.update(d.track_id, d.bbox, d.label, d.confidence, t)
            kind, severity = INTRUDER_CLASSES[track.label]
            item.update({
                "id": f"trk_{track.track_id}",
                "track_id": track.track_id,
                "label": track.label,
                "kind": kind,
                "severity": severity,
                "velocity": {"vx": round(track.vx, 4), "vy": round(track.vy, 4)},
                "hits": track.hits,
            })
            items.append(item)
            if not track.alerted and track.hits >= CONFIRM_HITS["intruder"]:
                track.alerted = True
                confirmed.append(item)
        self._intruders.prune(t)
        return items, confirmed

    def _defect_items(self, classified: list) -> tuple[list[dict], list[dict]]:
        tracks = self._defects.update([(info.defect_type, d.bbox) for d, info in classified])
        items, confirmed = [], []
        for (d, info), track in zip(classified, tracks, strict=True):
            item = {
                "id": f"def_{track.track_id}",
                "track_id": track.track_id,
                "category": "maintenance",
                "label": info.defect_type,
                "kind": info.defect_type,
                "title": info.title,
                "severity": info.severity,
                "confidence": round(d.confidence, 3),
                "bbox": _bbox(d.bbox),
                "area_fraction": info.area_fraction,
                "classifier": info.classifier,
                "velocity": None,
                "hits": track.hits,
            }
            items.append(item)
            if not track.alerted and track.hits >= CONFIRM_HITS["maintenance"]:
                track.alerted = True
                confirmed.append(item)
        return items, confirmed

    def _should_alert(self, stream: Stream, kind: str, position: dict | None) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last_alert.get((stream, kind))
            if last is not None and now - last[0] < COOLDOWN_S[stream]:
                last_pos = last[1]
                if position is None or last_pos is None or _distance_m(position, last_pos) < NEW_PLACE_M:
                    return False
            self._last_alert[(stream, kind)] = (now, position)
            return True

    def _within_issue_budget(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._issue_times and now - self._issue_times[0] > 60:
                self._issue_times.popleft()
            if len(self._issue_times) >= MAX_ISSUES_PER_MINUTE:
                return False
            self._issue_times.append(now)
            return True

    def _alert(self, stream: Stream, frame: Frame, item: dict, position: dict | None, detector: str) -> None:
        if not self._should_alert(stream, item["kind"], position):
            return
        ctx = self.context()
        title = self._title(item)
        issue_id = None
        if ctx.get("auto_issues") and self.issue_sink is not None and self._within_issue_budget():
            try:
                issue_id = self.issue_sink.create(
                    category=item["category"],
                    title=title,
                    description=self._description(stream, frame, item, position, detector, ctx),
                    severity=item["severity"],
                    location=self._location(frame, position, ctx),
                    snapshot=render_snapshot(frame, item),
                    filename=f"detection-{item['label']}-{item['track_id']}.jpg",
                )
                self.issues_created += 1
            except Exception:
                log.exception("failed to log auto-detected issue")
        self.alerts += 1
        self.publish({
            "type": "alert",
            "stream": stream,
            "category": item["category"],
            "title": title,
            "label": item["label"],
            "severity": item["severity"],
            "confidence": item["confidence"],
            "track_id": item["track_id"],
            "issue_id": issue_id,
            "frame_ts": iso(frame.ts),
            "media_time": frame.media_time,
            "position": position,
        })

    @staticmethod
    def _title(item: dict) -> str:
        if item["category"] == "maintenance":
            return f"{item['title']} detected"
        if item["kind"] == "person":
            return "Person detected"
        return f"Vehicle detected ({item['label']})"

    @staticmethod
    def _location(frame: Frame, position: dict | None, ctx: dict) -> str:
        if position:
            return f"{position['lat']:.6f}, {position['lon']:.6f}"
        if frame.media_time is not None and ctx.get("video_title"):
            return f"Test video at {_clock(frame.media_time)}"
        return ""

    @staticmethod
    def _description(stream: Stream, frame: Frame, item: dict, position: dict | None, detector: str,
                     ctx: dict) -> str:
        what = "intruder detection, ByteTrack" if stream == "intruder" else "maintenance detection, defect"
        lines = [
            "Auto-detected by the ground station.",
            f"Detector: {detector} ({what} #{item['track_id']})",
            f"Confidence: {item['confidence']:.2f}, confirmed in {item['hits']} inference frames",
        ]
        if stream == "maintenance":
            lines.append(f"Defect: {item['title']}, covering {item['area_fraction'] * 100:.1f}% of the frame")
            if item.get("classifier"):
                lines.append(f"Defect classifier: {item['classifier']}")
        frame_line = f"Frame time: {iso(frame.ts)}"
        if frame.media_time is not None and ctx.get("video_title"):
            frame_line += f' (at {_clock(frame.media_time)} in test video "{ctx["video_title"]}")'
        lines.append(frame_line)
        if position:
            pos = f"Position: {position['lat']:.6f}, {position['lon']:.6f}"
            if position.get("alt_m") is not None:
                pos += f", altitude {position['alt_m']:.0f} m"
            if position.get("heading_deg") is not None:
                pos += f", heading {position['heading_deg']:.0f}°"
            lines.append(pos)
        else:
            lines.append("Position: no GPS fix")
        if ctx.get("mode"):
            lines.append(f"Flight mode: {MODE_LABELS.get(ctx['mode'], ctx['mode'])}")
        if ctx.get("source_label"):
            lines.append(f"Source: {ctx['source_label']}")
        return "\n".join(lines)
