import logging
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import catalog_options, load_catalog
from app.db import connect
from app.recommendations import recommend
from app.schemas import Contractor, HealthResponse, OptionsResponse, RecommendationRequest, RecommendationResponse

logger = logging.getLogger(__name__)
app = FastAPI(
    title="pop-Eyes API",
    version="0.2.0",
    description="Database-backed contractor selection with strict filters and an optional AI module.",
)


@app.exception_handler(psycopg.Error)
async def database_error_handler(request: Request, exc: psycopg.Error) -> JSONResponse:
    # Never expose connection parameters or raw database errors to the client.
    logger.warning("Database request failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": "database_unavailable", "message": "База данных временно недоступна."}},
    )


@app.get("/health", response_model=HealthResponse, tags=["Infrastructure"])
def health() -> dict:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT dataset_version, profile_count,
                   (SELECT count(*) FROM contractors) AS actual_count,
                   to_regclass('recommendation_results') IS NOT NULL AS recommendation_schema_ready
            FROM dataset_metadata WHERE singleton = TRUE
            """
        ).fetchone()
    if row is None or row["actual_count"] == 0 or row["actual_count"] != row["profile_count"]:
        raise HTTPException(status_code=503, detail={"code": "dataset_not_ready"})
    if not row["recommendation_schema_ready"]:
        raise HTTPException(status_code=503, detail={"code": "recommendation_schema_not_ready"})
    return {
        "status": "ok",
        "database": "ok",
        "profiles_count": row["actual_count"],
        "dataset_version": row["dataset_version"],
    }


@app.get("/api/options", response_model=OptionsResponse, tags=["Catalog"])
def options() -> dict:
    metadata, candidates = load_catalog()
    return catalog_options(metadata, candidates)


@app.post("/api/recommendations", response_model=RecommendationResponse, tags=["Recommendations"])
async def recommendations(request: RecommendationRequest) -> dict:
    return await recommend(request)


@app.get("/api/contractors/{contractor_id}", response_model=Contractor, tags=["Catalog"])
def contractor(contractor_id: str) -> dict:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM contractors WHERE id = %s", (contractor_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "contractor_not_found"})
    return row


# API and Swagger routes take precedence; HTML, CSS and JS share the same origin.
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="frontend")
