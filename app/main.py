"""FastAPI application entry point.

Wires the routers, initialises the database, and serves a single-page UI from
``app/static``. Run with::

    python run.py
    # or
    uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.database import init_db
from app.routers import billing, coding, encounters, epic, patients, utilization

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    description=(
        "Inpatient & outpatient medical coding and billing with ICD-10 / CPT "
        "verification and Epic FHIR R4 integration."
    ),
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__, "app": settings.APP_NAME}


app.include_router(patients.router)
app.include_router(encounters.router)
app.include_router(coding.router)
app.include_router(billing.router)
app.include_router(epic.router)
app.include_router(utilization.router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/utilization", include_in_schema=False)
def utilization_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "utilization.html")


# Serve JS/CSS assets. Mounted last so it does not shadow the API routes.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
