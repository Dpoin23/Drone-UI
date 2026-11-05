"""Per-track bookkeeping on top of the detectors.

ByteTrack (inside Ultralytics) assigns intruder track IDs. :class:`TrackRegistry` adds what the
pipeline needs from them: how many inference frames confirmed a track, and its velocity, which
the UI uses to keep boxes moving between inference frames. Defects get IDs from
:class:`IouTracker`, a simple IoU matcher that is enough at 1-2 FPS for mostly static targets.
"""

from collections import Counter
from dataclasses import dataclass, field

Box = tuple[float, float, float, float]

VELOCITY_SMOOTHING = 0.5
MAX_SPEED = 2.0
"""Frame widths per second; anything faster is an ID switch, not motion."""


def iou(a: Box, b: Box) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    first_seen: float
    last_seen: float
    bbox: Box
    hits: int = 1
    vx: float = 0.0
    vy: float = 0.0
    best_confidence: float = 0.0
    labels: Counter = field(default_factory=Counter)
    alerted: bool = False

    @property
    def label(self) -> str:
        return self.labels.most_common(1)[0][0]


class TrackRegistry:
    def __init__(self, forget_after_s: float = 10.0) -> None:
        self.forget_after_s = forget_after_s
        self.tracks: dict[int, Track] = {}

    def reset(self) -> None:
        self.tracks.clear()

    def update(self, track_id: int, bbox: Box, label: str, confidence: float, t: float) -> Track:
        """Record an observation at time ``t`` (media time for recordings, wall clock for live)."""
        track = self.tracks.get(track_id)
        if track is None or t < track.last_seen:
            track = Track(track_id=track_id, first_seen=t, last_seen=t, bbox=bbox)
            self.tracks[track_id] = track
        else:
            dt = t - track.last_seen
            if dt > 0:
                cx, cy = bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2
                px, py = track.bbox[0] + track.bbox[2] / 2, track.bbox[1] + track.bbox[3] / 2
                vx, vy = (cx - px) / dt, (cy - py) / dt
                if abs(vx) <= MAX_SPEED and abs(vy) <= MAX_SPEED:
                    a = VELOCITY_SMOOTHING
                    track.vx = a * vx + (1 - a) * track.vx
                    track.vy = a * vy + (1 - a) * track.vy
            track.hits += 1
            track.last_seen = t
            track.bbox = bbox
        track.labels[label] += 1
        track.best_confidence = max(track.best_confidence, confidence)
        return track

    def prune(self, now: float) -> None:
        stale = [tid for tid, tr in self.tracks.items() if now - tr.last_seen > self.forget_after_s]
        for tid in stale:
            del self.tracks[tid]


@dataclass
class DefectTrack:
    track_id: int
    defect_type: str
    bbox: Box
    hits: int = 1
    misses: int = 0
    alerted: bool = False


class IouTracker:
    def __init__(self, min_iou: float = 0.3, max_misses: int = 3) -> None:
        self.min_iou = min_iou
        self.max_misses = max_misses
        self.tracks: list[DefectTrack] = []
        self._next_id = 1

    def reset(self) -> None:
        self.tracks.clear()

    def update(self, detections: list[tuple[str, Box]]) -> list[DefectTrack]:
        """Greedily match this frame's (type, box) pairs to existing tracks; returns one track each."""
        pairs = sorted(
            ((iou(tr.bbox, box), ti, di)
             for ti, tr in enumerate(self.tracks)
             for di, (kind, box) in enumerate(detections) if kind == tr.defect_type),
            reverse=True,
        )
        assigned: dict[int, DefectTrack] = {}
        used: set[int] = set()
        for score, ti, di in pairs:
            if score < self.min_iou:
                break
            if ti in used or di in assigned:
                continue
            track = self.tracks[ti]
            track.bbox = detections[di][1]
            track.hits += 1
            track.misses = 0
            assigned[di] = track
            used.add(ti)
        for ti, track in enumerate(self.tracks):
            if ti not in used:
                track.misses += 1
        self.tracks = [t for t in self.tracks if t.misses <= self.max_misses]
        for di, (kind, box) in enumerate(detections):
            if di not in assigned:
                track = DefectTrack(track_id=self._next_id, defect_type=kind, bbox=box)
                self._next_id += 1
                self.tracks.append(track)
                assigned[di] = track
        return [assigned[i] for i in range(len(detections))]
