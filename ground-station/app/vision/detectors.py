"""YOLO detectors for the two inference streams.

* **Intruder detection**: YOLOv8n trained on VisDrone (people and vehicles from the air), run with
  ByteTrack so each object keeps one identity between inference frames. Until VisDrone weights
  are trained, the stock COCO ``yolov8n.pt`` is used; its person and vehicle classes map onto the
  same labels.
* **Maintenance detection**: YOLOv8n trained on MBDD2025 (building defects), followed by defect
  classification in :mod:`app.vision.defects`.

Weights are not committed. ``tools/train.py`` produces them into ``models/``.
"""

import importlib.util
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import Settings
from .frames import Frame
from .modes import Stream

INTRUDER_WEIGHTS = ("yolov8n-visdrone.pt", "yolov8n.pt")
MAINTENANCE_WEIGHTS = ("yolov8n-mbdd2025.pt",)
TRACKER_CONFIG = "bytetrack.yaml"

# Model class name -> (kind, severity). VisDrone and COCO names both appear here.
INTRUDER_CLASSES: dict[str, tuple[str, str]] = {
    "person": ("person", "high"),
    "pedestrian": ("person", "high"),
    "people": ("person", "high"),
    "bicycle": ("vehicle", "medium"),
    "motorcycle": ("vehicle", "medium"),
    "motor": ("vehicle", "medium"),
    "car": ("vehicle", "medium"),
    "van": ("vehicle", "medium"),
    "truck": ("vehicle", "medium"),
    "bus": ("vehicle", "medium"),
    "tricycle": ("vehicle", "medium"),
    "awning-tricycle": ("vehicle", "medium"),
}

# ByteTrack associates low-confidence boxes too, so detection runs with a low threshold and
# only tracks above these are reported.
INTRUDER_MIN_CONF = 0.1
MAINTENANCE_MIN_CONF = 0.25


@dataclass(frozen=True)
class RawDetection:
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]
    """Normalized (x, y, w, h), top-left origin."""
    track_id: int | None = None


class Detector(Protocol):
    name: str
    device: str

    def detect(self, frame: Frame) -> list[RawDetection]: ...

    def reset(self) -> None: ...


class CropClassifier(Protocol):
    name: str

    def classify(self, frame: Frame, bbox: tuple[float, float, float, float]) -> tuple[str, float] | None: ...


class VisionUnavailable(RuntimeError):
    pass


def _resolve(models_dir: Path, configured: str, defaults: tuple[str, ...]) -> Path | None:
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else models_dir / path
    for name in defaults:
        if (models_dir / name).is_file():
            return models_dir / name
    return None


def intruder_weights(settings: Settings) -> Path:
    # Ultralytics downloads the stock yolov8n.pt into models/ on first use.
    return _resolve(settings.models_dir, settings.intruder_model, INTRUDER_WEIGHTS) or (
        settings.models_dir / INTRUDER_WEIGHTS[-1]
    )


def maintenance_weights(settings: Settings) -> Path | None:
    return _resolve(settings.models_dir, settings.maintenance_model, MAINTENANCE_WEIGHTS)


def ultralytics_installed() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("ultralytics", "cv2", "numpy"))


def capabilities(settings: Settings) -> dict:
    installed = ultralytics_installed()
    missing = None if installed else "Install requirements-vision.txt to enable image processing."
    intruder = intruder_weights(settings)
    maintenance = maintenance_weights(settings)
    stock = intruder.name == "yolov8n.pt"
    return {
        "installed": installed,
        "streams": {
            "intruder": {
                "available": installed,
                "model": intruder.name,
                "reason": missing,
                "note": "Stock COCO weights. Train VisDrone weights with tools/train.py for aerial footage."
                if stock else None,
            },
            "maintenance": {
                "available": installed and maintenance is not None and maintenance.is_file(),
                "model": maintenance.name if maintenance else None,
                "reason": missing or (
                    None if maintenance and maintenance.is_file()
                    else "No maintenance model yet. Train one on MBDD2025 with tools/train.py."
                ),
                "note": None,
            },
        },
    }


# ---- Ultralytics implementations -----------------------------------------------------------------

_load_lock = threading.Lock()


def _load_yolo(weights: Path, settings: Settings):
    if not ultralytics_installed():
        raise VisionUnavailable("Install requirements-vision.txt to enable image processing.")
    from ultralytics import YOLO

    weights.parent.mkdir(parents=True, exist_ok=True)
    # Loading touches shared Ultralytics settings and may download weights; one at a time.
    with _load_lock:
        return YOLO(str(weights))


def _predict_args(settings: Settings) -> dict:
    # No device means Ultralytics picks the first GPU if there is one, else the CPU.
    args: dict = {"imgsz": settings.vision_imgsz, "verbose": False}
    if settings.vision_device:
        args["device"] = settings.vision_device
    return args


def _boxes(result, track: bool) -> list[RawDetection]:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []
    h, w = result.orig_shape
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int)
    ids = boxes.id.cpu().numpy().astype(int) if track and boxes.id is not None else None
    names = result.names
    out = []
    for i in range(len(xyxy)):
        x1, y1, x2, y2 = (float(v) for v in xyxy[i])
        out.append(RawDetection(
            label=str(names[int(cls[i])]),
            confidence=float(conf[i]),
            bbox=(max(0.0, x1 / w), max(0.0, y1 / h), min(1.0, (x2 - x1) / w), min(1.0, (y2 - y1) / h)),
            track_id=int(ids[i]) if ids is not None else None,
        ))
    return out


class UltralyticsDetector:
    def __init__(self, weights: Path, settings: Settings, *, track: bool, min_conf: float,
                 keep: dict[str, object] | None = None) -> None:
        self.model = _load_yolo(weights, settings)
        self.name = weights.stem
        self.track = track
        names = self.model.names
        classes = [i for i, n in names.items() if n in keep] if keep else None
        if keep and not classes:
            raise VisionUnavailable(f"{weights.name} has none of the expected classes")
        self.args = {**_predict_args(settings), "conf": min_conf, "classes": classes}
        self._warm_up(settings.vision_imgsz)

    def _warm_up(self, imgsz: int) -> None:
        import numpy as np

        self.model.predict(np.zeros((imgsz, imgsz, 3), dtype=np.uint8), **self.args)
        self.device = str(self.model.device)

    def detect(self, frame: Frame) -> list[RawDetection]:
        image = frame.image()
        if self.track:
            results = self.model.track(image, persist=True, tracker=TRACKER_CONFIG, **self.args)
        else:
            results = self.model.predict(image, **self.args)
        return _boxes(results[0], self.track)

    def reset(self) -> None:
        predictor = getattr(self.model, "predictor", None)
        for tracker in getattr(predictor, "trackers", None) or []:
            tracker.reset()


class UltralyticsCropClassifier:
    """Optional second stage: a YOLO classification model run on each defect crop."""

    def __init__(self, weights: Path, settings: Settings) -> None:
        self.model = _load_yolo(weights, settings)
        self.name = weights.stem
        self.args = {**_predict_args(settings), "imgsz": 224}

    def classify(self, frame: Frame, bbox: tuple[float, float, float, float]) -> tuple[str, float] | None:
        image = frame.image()
        h, w = image.shape[:2]
        x, y, bw, bh = bbox
        # Pad the crop a little so the classifier sees the defect's surroundings.
        x1, y1 = int(max(0, (x - bw * 0.1) * w)), int(max(0, (y - bh * 0.1) * h))
        x2, y2 = int(min(w, (x + bw * 1.1) * w)), int(min(h, (y + bh * 1.1) * h))
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None
        result = self.model.predict(image[y1:y2, x1:x2], **self.args)[0]
        if result.probs is None:
            return None
        top = int(result.probs.top1)
        return str(result.names[top]), float(result.probs.top1conf)


def load_detector(stream: Stream, settings: Settings) -> Detector:
    if stream == "intruder":
        return UltralyticsDetector(
            intruder_weights(settings), settings, track=True, min_conf=INTRUDER_MIN_CONF, keep=INTRUDER_CLASSES
        )
    weights = maintenance_weights(settings)
    if weights is None or not weights.is_file():
        raise VisionUnavailable("No maintenance model yet. Train one on MBDD2025 with tools/train.py.")
    return UltralyticsDetector(weights, settings, track=False, min_conf=MAINTENANCE_MIN_CONF)


def load_crop_classifier(settings: Settings) -> CropClassifier | None:
    if not settings.defect_classifier:
        return None
    path = Path(settings.defect_classifier)
    path = path if path.is_absolute() else settings.models_dir / path
    if not path.is_file():
        raise VisionUnavailable(f"Defect classifier {path.name} not found")
    return UltralyticsCropClassifier(path, settings)
