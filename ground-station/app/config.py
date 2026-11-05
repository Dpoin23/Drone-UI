import os
from dataclasses import dataclass
from pathlib import Path

GROUND_STATION_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = GROUND_STATION_DIR.parent
DATA_DIR = GROUND_STATION_DIR / "data"
MODELS_DIR = GROUND_STATION_DIR / "models"


@dataclass(frozen=True)
class Settings:
    db_path: Path
    uploads_dir: Path
    videos_dir: Path
    web_dist: Path
    token_ttl_hours: int
    max_image_bytes: int = 10 * 1024 * 1024
    max_images_per_issue: int = 20
    max_video_bytes: int = 4 * 1024 * 1024 * 1024
    models_dir: Path = MODELS_DIR
    # Weights paths; empty picks the default file in models_dir (see app/vision/detectors.py).
    intruder_model: str = ""
    maintenance_model: str = ""
    defect_classifier: str = ""
    vision_device: str = ""
    vision_imgsz: int = 640
    vision_max_sessions: int = 2
    # A trusted GStreamer pipeline ending in appsink, used instead of the stream URL when set.
    capture_pipeline: str = ""


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        db_path=Path(env("DRONE_UI_DB", DATA_DIR / "drone-ui.db")),
        uploads_dir=Path(env("DRONE_UI_UPLOADS", DATA_DIR / "uploads")),
        videos_dir=Path(env("DRONE_UI_VIDEOS", DATA_DIR / "videos")),
        web_dist=Path(env("DRONE_UI_WEB_DIST", REPO_DIR / "web" / "dist")),
        token_ttl_hours=int(env("DRONE_UI_TOKEN_TTL_HOURS", "168")),
        max_video_bytes=int(env("DRONE_UI_MAX_VIDEO_MB", "4096")) * 1024 * 1024,
        models_dir=Path(env("DRONE_UI_MODELS", MODELS_DIR)),
        intruder_model=env("DRONE_UI_INTRUDER_MODEL", ""),
        maintenance_model=env("DRONE_UI_MAINTENANCE_MODEL", ""),
        defect_classifier=env("DRONE_UI_DEFECT_CLASSIFIER", ""),
        vision_device=env("DRONE_UI_VISION_DEVICE", ""),
        vision_imgsz=int(env("DRONE_UI_VISION_IMGSZ", "640")),
        vision_max_sessions=int(env("DRONE_UI_VISION_MAX_SESSIONS", "2")),
        capture_pipeline=env("DRONE_UI_CAPTURE_PIPELINE", ""),
    )
