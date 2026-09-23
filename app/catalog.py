"""Read a consistent, typed catalog snapshot (the MVP contains 66 profiles)."""

from fastapi import HTTPException

from app.db import connect
from app.schemas import Contractor


def load_catalog() -> tuple[dict, list[dict]]:
    with connect() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        metadata = connection.execute("SELECT * FROM dataset_metadata WHERE singleton = TRUE").fetchone()
        rows = connection.execute("SELECT * FROM contractors ORDER BY id").fetchall()
    if not metadata or not rows or len(rows) != metadata["profile_count"]:
        raise HTTPException(status_code=503, detail={"code": "dataset_not_ready"})
    return metadata, [Contractor.model_validate(row).model_dump(mode="json") for row in rows]


def catalog_options(metadata: dict, candidates: list[dict]) -> dict:
    return {
        "cities": sorted({c["city"] for c in candidates}),
        "categories": sorted({value for c in candidates for value in c["categories"]}),
        "event_types": sorted({value for c in candidates for value in c["event_formats"]}),
        "languages": sorted({value for c in candidates for value in c["languages"]}),
        "date_min": metadata["calendar_start"],
        "date_max": metadata["calendar_end"],
        "dataset_version": metadata["dataset_version"],
    }
