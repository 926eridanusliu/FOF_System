from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine, upgrade_existing_schema
from app import models  # noqa: F401 - registers tables with SQLAlchemy metadata
from app.routers.managers import router as managers_router
from app.routers.products import router as products_router
from app.routers.reports import file_router, router as reports_router
from app.routers.report_versions import router as report_versions_router
from app.routers.scorecards import router as scorecards_router
from app.services.generation_queue import recover_generation_jobs
from app.routers.notifications import router as notifications_router
from app.routers.invitations import router as invitations_router
from app.routers.deletions import router as deletions_router
from app.services.feishu_notifications import recover_notifications


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize database tables when the application starts."""
    Base.metadata.create_all(bind=engine)
    upgrade_existing_schema()
    recover_generation_jobs(engine)
    recover_notifications(engine)
    yield


app = FastAPI(
    title="FOF Due Diligence Report Service",
    description="Backend service for managing and generating FOF due diligence reports.",
    version="0.5.0",
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(managers_router)
app.include_router(products_router)
app.include_router(reports_router)
app.include_router(report_versions_router)
app.include_router(scorecards_router)
app.include_router(notifications_router)
app.include_router(invitations_router)
app.include_router(deletions_router)
app.include_router(file_router)


@app.get("/health", tags=["System"], summary="Service health check")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "fof-report-backend",
    }


# The runnable delivery includes the production-built Vue files here. Keeping
# this after every API router lets one Uvicorn service host both UI and API,
# while the catch-all still supports Vue history-mode routes such as /fill/....
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend_spa(frontend_path: str) -> FileResponse:
        candidate = (FRONTEND_DIST / frontend_path).resolve()
        if candidate.is_relative_to(FRONTEND_DIST.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
