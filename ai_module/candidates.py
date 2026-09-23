"""Normalize the agreed candidate contract, including PostgreSQL NUMERIC."""

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Any


def normalize_candidate(candidate: Mapping[str, Any]) -> dict:
    """Return a copy suitable for JSON; never parse CSV, filter, or mutate input."""
    result = {}
    for field in ("id", "anon_name", "city", "description"):
        value = candidate[field]
        if not isinstance(value, str) or (field != "description" and not value.strip()):
            raise ValueError(f"Candidate {field} must be a string")
        result[field] = value
    for field in ("categories", "event_formats", "languages"):
        value = candidate[field]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"Candidate {field} must be a list of strings")
        result[field] = list(value)
    for field in ("synthetic", "city_imputed", "price_imputed"):
        if type(candidate[field]) is not bool:
            raise ValueError(f"Candidate {field} must be boolean")
        result[field] = candidate[field]
    price = candidate["price_from_kzt"]
    if type(price) is not int or price < 0:
        raise ValueError("Candidate price must be a nonnegative integer")
    result["price_from_kzt"] = price
    hours = candidate["max_hours"]
    if hours is not None:
        if isinstance(hours, bool) or not isinstance(hours, (int, float, Decimal)):
            raise ValueError("Candidate max_hours must be numeric or None")
        hours = float(hours)
        if not math.isfinite(hours) or hours <= 0:
            raise ValueError("Candidate max_hours must be positive and finite")
    result["max_hours"] = hours
    return result
