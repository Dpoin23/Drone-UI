import os
from dataclasses import dataclass
from pathlib import Path

GROUND_STATION_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = GROUND_STATION_DIR.parent
DATA_DIR = GROUND_STATION_DIR / "data"


@dataclass(frozen=True)
class Settings:
    db_path: Path
    uploads_dir: Path
    web_dist: Path
    token_ttl_hours: int
    max_image_bytes: int = 10 * 1024 * 1024
    max_images_per_issue: int = 20


def load_settings() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("DRONE_UI_DB", DATA_DIR / "drone-ui.db")),
        uploads_dir=Path(os.environ.get("DRONE_UI_UPLOADS", DATA_DIR / "uploads")),
        web_dist=Path(os.environ.get("DRONE_UI_WEB_DIST", REPO_DIR / "web" / "dist")),
        token_ttl_hours=int(os.environ.get("DRONE_UI_TOKEN_TTL_HOURS", "168")),
    )
