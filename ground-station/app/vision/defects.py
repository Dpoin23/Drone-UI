"""Defect classification for maintenance detections.

The detector's class gives the defect type (MBDD2025: crack, leakage, abscission, corrosion,
bulge). This step normalizes that type, optionally refines it with a crop classifier, and grades
severity from the type and how much of the frame the defect covers.
"""

from dataclasses import dataclass

from .detectors import CropClassifier, RawDetection
from .frames import Frame

SEVERITIES = ("low", "medium", "high", "critical")

DEFECT_TYPES: dict[str, dict[str, str]] = {
    "crack": {"title": "Crack", "severity": "medium"},
    "leakage": {"title": "Leakage", "severity": "medium"},
    # Detached facade material can fall on people below.
    "abscission": {"title": "Abscission (detached material)", "severity": "high"},
    "corrosion": {"title": "Corrosion", "severity": "medium"},
    # Bulging usually precedes detachment.
    "bulge": {"title": "Bulging", "severity": "high"},
    "other": {"title": "Surface defect", "severity": "low"},
}

_ALIASES = {
    "cracks": "crack",
    "leak": "leakage",
    "leaking": "leakage",
    "water_leakage": "leakage",
    "spalling": "abscission",
    "peeling": "abscission",
    "detachment": "abscission",
    "rust": "corrosion",
    "bulging": "bulge",
    "bulges": "bulge",
}

_SEVERITY_WORDS = {
    "minor": "low", "low": "low", "light": "low",
    "moderate": "medium", "medium": "medium",
    "severe": "high", "high": "high", "major": "high",
    "critical": "critical",
}

LARGE_AREA = 0.15
SMALL_AREA = 0.005


@dataclass(frozen=True)
class DefectInfo:
    defect_type: str
    title: str
    severity: str
    area_fraction: float
    classifier: str | None = None
    classifier_confidence: float | None = None


def normalize_defect(label: str) -> str:
    key = label.strip().lower().replace(" ", "_").replace("-", "_")
    key = _ALIASES.get(key, key)
    return key if key in DEFECT_TYPES else "other"


def _shift(severity: str, steps: int) -> str:
    i = SEVERITIES.index(severity) + steps
    return SEVERITIES[min(max(i, 0), len(SEVERITIES) - 1)]


def classify_defect(det: RawDetection, frame: Frame | None = None,
                    crop_classifier: CropClassifier | None = None) -> DefectInfo:
    defect_type = normalize_defect(det.label)
    severity_override = None
    cls_label = cls_conf = None
    if crop_classifier is not None and frame is not None:
        result = crop_classifier.classify(frame, det.bbox)
        if result:
            cls_label, cls_conf = result
            words = cls_label.lower().replace("-", "_").split("_")
            refined = normalize_defect("_".join(w for w in words if w not in _SEVERITY_WORDS))
            if refined != "other":
                defect_type = refined
            severity_override = next((_SEVERITY_WORDS[w] for w in words if w in _SEVERITY_WORDS), None)

    area = det.bbox[2] * det.bbox[3]
    severity = DEFECT_TYPES[defect_type]["severity"]
    if severity_override:
        severity = severity_override
    elif area >= LARGE_AREA:
        severity = _shift(severity, 1)
    elif area < SMALL_AREA and det.confidence < 0.5:
        severity = _shift(severity, -1)
    return DefectInfo(
        defect_type=defect_type,
        title=DEFECT_TYPES[defect_type]["title"],
        severity=severity,
        area_fraction=round(area, 4),
        classifier=cls_label,
        classifier_confidence=round(cls_conf, 3) if cls_conf is not None else None,
    )
