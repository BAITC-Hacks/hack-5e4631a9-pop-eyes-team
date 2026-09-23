"""Shared deterministic evidence builder; no network or database access."""

import json
import re
from collections.abc import Mapping
from typing import Any

EVIDENCE_VERSION = "evidence-v1"

_LABELS = {
    "anon_name": "Имя в каталоге",
    "city": "Город",
    "categories": "Категории",
    "price_from_kzt": "Начальная цена, тенге (не окончательная стоимость)",
    "event_formats": "Форматы мероприятий",
    "languages": "Языки",
    "max_hours": "Максимальная длительность присутствия, часов",
    "synthetic": "Синтетический профиль",
    "city_imputed": "Город подставлен в исходных данных",
    "price_imputed": "Цена подставлена в исходных данных",
}


def build_evidence(candidate: Mapping[str, Any]) -> dict[str, str]:
    """Return canonical facts for an unchanged, normalized candidate.

    Description splitting preserves all text except insignificant whitespace.
    IDs are scoped to a candidate. They are stable within a dataset version,
    not across edits to its description. Call this same function on the backend.
    """
    candidate_id = candidate["id"]
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("Candidate id must be a nonempty string")
    description = candidate["description"]
    if not isinstance(description, str):
        raise ValueError("Candidate description must be a string")

    evidence = {}
    for field, label in _LABELS.items():
        value = candidate[field]
        if field == "max_hours" and value is None:
            text = "Ограничение длительности присутствия неприменимо (NULL)."
        else:
            text = f"{label}: {json.dumps(value, ensure_ascii=False, allow_nan=False)}"
        evidence[f"{candidate_id}:field:{field}"] = text

    fragments = re.split(r"(?<=[.!?])\s+|[\r\n]+", description.strip())
    fragments = [" ".join(fragment.split()) for fragment in fragments if fragment.strip()]
    for index, fragment in enumerate(fragments, start=1):
        evidence[f"{candidate_id}:description:{index}"] = fragment
    return evidence
