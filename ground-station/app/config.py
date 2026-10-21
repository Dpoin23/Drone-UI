import os
from dataclasses import dataclass
from pathlib import Path

GROUND_STATION_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = GROUND_STATION_DIR.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path
    web_dist: Path
    token_ttl_hours: int


def load_settings() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("DRONE_UI_DB", GROUND_STATION_DIR / "data" / "drone-ui.db")),
        web_dist=Path(os.environ.get("DRONE_UI_WEB_DIST", REPO_DIR / "web" / "dist")),
        token_ttl_hours=int(os.environ.get("DRONE_UI_TOKEN_TTL_HOURS", "168")),
    )
