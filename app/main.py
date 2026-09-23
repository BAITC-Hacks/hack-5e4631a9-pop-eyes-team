import logging

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.db import connect
from app.schemas import Contractor, HealthResponse, OptionsResponse

logger = logging.getLogger(__name__)
app = FastAPI(
    title="pop-Eyes API",
    version="0.1.0",
    description="Infrastructure and contractor catalog. AI recommendations are the next stage.",
)


@app.exception_handler(psycopg.Error)
async def database_error_handler(request: Request, exc: psycopg.Error) -> JSONResponse:
    # Never expose connection parameters or raw database errors to the client.
    logger.warning("Database request failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": "database_unavailable", "message": "База данных временно недоступна."}},
    )


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse, tags=["Infrastructure"])
def health() -> dict:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT dataset_version, profile_count,
                   (SELECT count(*) FROM contractors) AS actual_count
            FROM dataset_metadata WHERE singleton = TRUE
            """
        ).fetchone()
    if row is None or row["actual_count"] == 0 or row["actual_count"] != row["profile_count"]:
        raise HTTPException(status_code=503, detail={"code": "dataset_not_ready"})
    return {
        "status": "ok",
        "database": "ok",
        "profiles_count": row["actual_count"],
        "dataset_version": row["dataset_version"],
    }


@app.get("/api/options", response_model=OptionsResponse, tags=["Catalog"])
def options() -> dict:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                ARRAY(SELECT DISTINCT city FROM contractors ORDER BY city) AS cities,
                ARRAY(SELECT DISTINCT unnest(categories) AS value FROM contractors ORDER BY value) AS categories,
                ARRAY(SELECT DISTINCT unnest(event_formats) AS value FROM contractors ORDER BY value) AS event_types,
                ARRAY(SELECT DISTINCT unnest(languages) AS value FROM contractors ORDER BY value) AS languages,
                calendar_start, calendar_end, dataset_version
            FROM dataset_metadata WHERE singleton = TRUE
            """
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=503, detail={"code": "dataset_not_ready"})
    return {
        "cities": row["cities"],
        "categories": row["categories"],
        "event_types": row["event_types"],
        "languages": row["languages"],
        "calendar_window": {"start": row["calendar_start"], "end": row["calendar_end"]},
        "dataset_version": row["dataset_version"],
    }


@app.get("/api/contractors/{contractor_id}", response_model=Contractor, tags=["Catalog"])
def contractor(contractor_id: str) -> dict:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM contractors WHERE id = %s", (contractor_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "contractor_not_found"})
    return row
