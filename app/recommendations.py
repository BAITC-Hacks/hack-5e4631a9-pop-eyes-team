"""Strict filtering, validated selection and persistent, versioned responses."""

import hashlib
import json
import os

from fastapi.exceptions import RequestValidationError
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from app.catalog import catalog_options, load_catalog
from app.db import connect
from app.ranking import select_candidates
from app.schemas import RecommendationRequest, RecommendationResponse


def validate_catalog_request(request: RecommendationRequest, metadata: dict, candidates: list[dict]) -> None:
    options = catalog_options(metadata, candidates)
    errors = []
    for field, key in (("city", "cities"), ("category", "categories"),
                       ("event_type", "event_types"), ("language", "languages")):
        value = getattr(request, field)
        if value is not None and value not in options[key]:
            errors.append({"type": "value_error", "loc": ("body", field),
                           "msg": "Выберите значение из справочника.", "input": value})
    if not options["date_min"] <= request.date <= options["date_max"]:
        errors.append({"type": "value_error", "loc": ("body", "date"),
                       "msg": f"Доступность известна с {options['date_min']} по {options['date_max']}.",
                       "input": request.date.isoformat()})
    if errors:
        raise RequestValidationError(errors)


def filter_candidates(request: dict, candidates: list[dict]) -> tuple[int, list[dict], dict]:
    in_category = [c for c in candidates if c["city"] == request["city"] and request["category"] in c["categories"]]
    excluded = dict.fromkeys(("date", "budget", "event_type", "duration", "language"), 0)
    eligible = []
    for c in in_category:
        failed = None
        if request["date"] in c["busy_dates"]:
            failed = "date"
        elif c["price_from_kzt"] > request["budget_kzt"]:
            failed = "budget"
        elif request["event_type"] not in c["event_formats"]:
            failed = "event_type"
        elif (request["duration_hours"] is not None and c["max_hours"] is not None
              and request["duration_hours"] > c["max_hours"]):
            failed = "duration"
        elif request["language"] is not None and request["language"] not in c["languages"]:
            failed = "language"
        if failed:
            excluded[failed] += 1
        else:
            eligible.append(c)
    return len(in_category), sorted(eligible, key=lambda c: c["id"]), excluded


def digest(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def recommendation_version() -> str:
    config = {"rules": "backend-v1", "ai_module": os.environ.get("AI_MODULE", "").strip(),
              "ai_version": os.environ.get("AI_VERSION", "v1"),
              "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
              "mode": os.environ.get("AI_MODE", "auto"),
              "timeout": os.environ.get("AI_TIMEOUT_SECONDS", "5")}
    return "backend-v1-" + digest(config)[:16]


def request_key(request: dict, dataset_version: str, version: str) -> str:
    return digest({"request": request, "dataset_version": dataset_version, "recommendation_version": version})


def cached_response(key: str) -> dict | None:
    with connect() as connection:
        row = connection.execute("SELECT response FROM recommendation_results WHERE request_key = %s", (key,)).fetchone()
    return dict(row["response"], cache_hit=True) if row else None


def save_response(key: str, request: dict, response: dict) -> dict:
    with connect() as connection:
        inserted = connection.execute(
            """INSERT INTO recommendation_results
               (request_key, request_payload, dataset_version, recommendation_version, response)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT (request_key) DO NOTHING
               RETURNING request_key""",
            (key, Jsonb(request), response["dataset_version"], response["recommendation_version"], Jsonb(response)),
        ).fetchone()
        # A separate statement sees the committed winner after a concurrent insert.
        stored = connection.execute("SELECT response FROM recommendation_results WHERE request_key = %s", (key,)).fetchone()
    return dict(stored["response"], cache_hit=inserted is None)


async def recommend(request: RecommendationRequest) -> dict:
    metadata, candidates = await run_in_threadpool(load_catalog)
    validate_catalog_request(request, metadata, candidates)
    payload = request.model_dump(mode="json")
    version = recommendation_version()
    key = request_key(payload, metadata["dataset_version"], version)
    cached = await run_in_threadpool(cached_response, key)
    if cached:
        return cached
    total, eligible, excluded = filter_candidates(payload, candidates)
    response = {
        "status": "category_absent" if not total else "no_matches",
        "message": ("В выбранном городе нет подрядчиков этой категории." if not total else
                    "Категория есть в городе, но никто не прошёл заданные условия."),
        "cards": [], "total_in_city_category": total, "eligible_count": len(eligible),
        "excluded_counts": excluded, "selection_mode": None, "cache_hit": False,
        "dataset_version": metadata["dataset_version"], "recommendation_version": version,
    }
    if eligible:
        ranking = await select_candidates(payload, eligible)
        by_id = {c["id"]: c for c in eligible}
        response.update(status="matched", selection_mode=ranking.selection_mode)
        response["message"] = (
            "AI сравнил всех допустимых кандидатов и выбрал подходящие варианты." if ranking.selection_mode == "ai" else
            "Резервный подбор без AI: обязательные условия проверены, порядок — по начальной цене. "
            "Пожелания к стилю и контексту в этом режиме не оцениваются."
        )
        for selected in ranking.selected:
            c = by_id[selected.id]
            response["cards"].append({
                "id": c["id"], "name": c["anon_name"], "categories": c["categories"], "city": c["city"],
                "price_from_kzt": c["price_from_kzt"], "reason": selected.reason, "evidence_ids": selected.evidence_ids,
                "synthetic": c["synthetic"], "city_imputed": c["city_imputed"], "price_imputed": c["price_imputed"],
            })
    validated = RecommendationResponse.model_validate(response).model_dump(mode="json")
    return await run_in_threadpool(save_response, key, payload, validated)
