from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .api import auth_routes, issues, stream
from .config import Settings, load_settings
from .storage.db import init_db


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings.db_path)
        yield

    app = FastAPI(title="Drone-UI ground station", lifespan=lifespan)
    app.state.settings = settings

    app.include_router(auth_routes.router)
    app.include_router(issues.router)
    app.include_router(stream.router)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    dist = settings.web_dist
    if (dist / "index.html").is_file():

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
