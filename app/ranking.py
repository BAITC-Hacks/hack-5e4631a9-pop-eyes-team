"""AI integration boundary; all candidates have already passed strict filters."""

import asyncio
import copy
import importlib
import inspect
import logging
import os
import re

from app.schemas import RankingResult

logger = logging.getLogger(__name__)


def build_evidence(candidate: dict) -> dict[str, str]:
    """Stable fact IDs shared by backend and the future AI module."""
    prefix = candidate["id"]
    facts = {
        f"{prefix}:city": candidate["city"],
        f"{prefix}:categories": " | ".join(candidate["categories"]),
        f"{prefix}:price_from_kzt": str(candidate["price_from_kzt"]),
        f"{prefix}:event_formats": " | ".join(candidate["event_formats"]),
        f"{prefix}:languages": " | ".join(candidate["languages"]),
        f"{prefix}:max_hours": str(candidate["max_hours"]),
        f"{prefix}:busy_dates": " | ".join(candidate["busy_dates"]),
    }
    fragments = re.split(r"(?<=[.!?])\s+|\n+", candidate["description"].strip())
    for index, fragment in enumerate(filter(None, fragments), start=1):
        facts[f"{prefix}:description:{index}"] = fragment
    return facts


def validate_ranking(raw: dict, candidates: list[dict], evidence: dict[str, dict]) -> RankingResult:
    result = RankingResult.model_validate(raw)
    allowed = {candidate["id"] for candidate in candidates}
    ids = [selected.id for selected in result.selected]
    if len(ids) != min(3, len(allowed)) or len(set(ids)) != len(ids) or not set(ids) <= allowed:
        raise ValueError("Ranking must contain exactly min(3, eligible_count) unique eligible IDs")
    for selected in result.selected:
        if len(set(selected.evidence_ids)) != len(selected.evidence_ids):
            raise ValueError("Duplicate evidence IDs")
        if not set(selected.evidence_ids) <= set(evidence[selected.id]):
            raise ValueError("Evidence does not belong to the selected candidate")
    return result


def fallback_ranking(request: dict, candidates: list[dict]) -> RankingResult:
    selected = []
    for candidate in sorted(candidates, key=lambda c: (c["price_from_kzt"], c["id"]))[:3]:
        cid = candidate["id"]
        evidence = build_evidence(candidate)
        ids = [f"{cid}:price_from_kzt", f"{cid}:busy_dates"]
        reason = (
            f"Проходит обязательные условия на {request['date']}; "
            f"начальная цена — {candidate['price_from_kzt']:,} ₸."
        ).replace(",", " ")
        description_id = f"{cid}:description:1"
        if description_id in evidence:
            reason += f" Из описания: «{evidence[description_id]}»"
            ids.append(description_id)
        selected.append({"id": cid, "reason": reason, "evidence_ids": ids})
    return RankingResult(selection_mode="fallback", selected=selected)


async def select_candidates(request: dict, candidates: list[dict]) -> RankingResult:
    module_name = os.environ.get("AI_MODULE", "").strip()
    if not module_name or os.environ.get("AI_MODE", "auto") == "fallback":
        return fallback_ranking(request, candidates)
    try:
        module = importlib.import_module(module_name)
        rank = module.rank_candidates
        if not inspect.iscoroutinefunction(rank):
            raise TypeError("rank_candidates must be async")
        # A teammate can export their shared helper; otherwise use the default IDs above.
        evidence_builder = getattr(module, "build_evidence", build_evidence)
        evidence = {c["id"]: evidence_builder(copy.deepcopy(c)) for c in candidates}
        if any(not isinstance(facts, dict) or not facts or
               any(not isinstance(k, str) or not isinstance(v, str) for k, v in facts.items())
               for facts in evidence.values()):
            raise ValueError("build_evidence must return a nonempty dict[str, str]")
        payload = [dict(copy.deepcopy(c), name=c["anon_name"], evidence=copy.deepcopy(evidence[c["id"]]))
                   for c in candidates]
        timeout = float(os.environ.get("AI_TIMEOUT_SECONDS", "5"))
        if not 0 < timeout <= 30:
            raise ValueError("AI_TIMEOUT_SECONDS must be in (0, 30]")
        raw = await asyncio.wait_for(rank(copy.deepcopy(request), payload), timeout=timeout)
        return validate_ranking(raw, candidates, evidence)
    except Exception as exc:
        # Do not log preferences, keys, model payloads or exception messages.
        logger.warning("AI ranking unavailable or invalid; using fallback (%s)", type(exc).__name__)
        return fallback_ranking(request, candidates)
