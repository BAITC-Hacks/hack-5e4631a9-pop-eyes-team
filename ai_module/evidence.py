"""Shared deterministic evidence builder; no network or database access."""

import json
import re
import textwrap
from collections.abc import Mapping
from typing import Any

from .candidates import normalize_candidate

EVIDENCE_VERSION = "evidence-v3"

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
    candidate = normalize_candidate(candidate)
    candidate_id = candidate["id"]
    description = candidate["description"]

    evidence = {}
    for field, label in _LABELS.items():
        value = candidate[field]
        if field == "max_hours" and value is None:
            text = "Ограничение длительности присутствия неприменимо (NULL)."
        else:
            text = f"{label}: {json.dumps(value, ensure_ascii=False, allow_nan=False)}"
        evidence[f"{candidate_id}:field:{field}"] = text

    sentences = re.split(r"(?<=[.!?])\s+|[\r\n]+|\s+(?=•)", description.strip())
    # Short references keep two exact quotes within the explanation budget.
    # Never truncate or split inside a word: pathological long tokens can still
    # exceed the quote budget and will be rejected if selected by the model.
    fragments = [
        part
        for sentence in sentences if sentence.strip()
        for part in textwrap.wrap(
            " ".join(sentence.split()), width=180,
            break_long_words=False, break_on_hyphens=False,
        )
    ]
    for index, fragment in enumerate(fragments, start=1):
        evidence[f"{candidate_id}:description:{index}"] = fragment
    return evidence
