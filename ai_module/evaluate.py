"""Evaluate real catalog fixtures. Offline by default; --live calls the API."""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from . import RECOMMENDATION_VERSION, build_evidence, rank_candidates

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests/fixtures/ai"


def check_result(fixture, result, *, live):
    """Machine-checkable checks, not a claim of semantic correctness."""
    errors = []
    candidates = {profile["id"]: profile for profile in fixture["eligible_candidates"]}
    selected = result["selected"]
    ids = [item["id"] for item in selected]
    if len(ids) != min(3, len(candidates)) or len(ids) != len(set(ids)):
        errors.append("wrong_count_or_duplicate_ids")
    if any(candidate_id not in candidates for candidate_id in ids):
        return errors + ["unknown_id"]
    for item in selected:
        facts = build_evidence(candidates[item["id"]])
        if not item["reason"].strip() or not item["evidence_ids"] or any(ref not in facts for ref in item["evidence_ids"]):
            errors.append(f"invalid_explanation_or_evidence:{item['id']}")
    if live and candidates:
        if result["selection_mode"] != "ai":
            errors.append("expected_ai_got_fallback")
        else:
            quality = fixture["_meta"].get("quality_checks", {})
            if quality.get("first_in") and (not ids or ids[0] not in quality["first_in"]):
                errors.append("first_candidate_does_not_meet_context_rubric")
            for preferred, other in quality.get("prefer_before", []):
                if other in ids and (preferred not in ids or ids.index(preferred) > ids.index(other)):
                    errors.append(f"context_priority:{preferred}_before_{other}")
    elif not live:
        if result["selection_mode"] != "fallback":
            errors.append("expected_fallback")
        if ids != fixture["_meta"]["expected_fallback_ids"]:
            errors.append("unexpected_fallback_order")
    return errors


async def run(args):
    if args.live and not os.getenv("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY is missing; load .env into the process environment first")
    paths = sorted(FIXTURE_DIR.glob("*.json"))
    if args.cases:
        by_name = {path.stem: path for path in paths}
        unknown = set(args.cases) - by_name.keys()
        if unknown:
            raise SystemExit("Unknown cases: " + ", ".join(sorted(unknown)))
        paths = [by_name[name] for name in args.cases]
    if not paths:
        raise SystemExit("No fixtures: run scripts/build_ai_fixtures.py first")
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "live": args.live, "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "timeout_seconds": float(os.getenv("AI_TIMEOUT_SECONDS", "8")),
        "recommendation_version": RECOMMENDATION_VERSION,
        "scope": "Isolated AI module; not database, HTTP filtering or cache verification",
        "cases": [],
    }
    for path in paths:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        started = time.perf_counter()
        with patch.dict(os.environ, {"AI_MODE": "auto" if args.live else "fallback"}):
            result = await rank_candidates(fixture["request"], fixture["eligible_candidates"])
        elapsed = round(time.perf_counter() - started, 3)
        errors = check_result(fixture, result, live=args.live)
        profiles = {profile["id"]: profile for profile in fixture["eligible_candidates"]}
        evidence = {item["id"]: {ref: build_evidence(profiles[item["id"]])[ref]
                                  for ref in item["evidence_ids"]} for item in result["selected"]}
        report["cases"].append({
            "name": path.stem, "source_sha256_lf": fixture["_meta"]["source_sha256_lf"],
            "request": fixture["request"], "eligible_ids": sorted(profiles),
            "elapsed_seconds": elapsed, "result": result, "cited_facts": evidence,
            "automated_check_errors": errors,
        })
        print(f"{path.stem}: {result['selection_mode']}, {elapsed}s, errors={errors}", flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report saved: {args.output}")
    if any(case["automated_check_errors"] for case in report["cases"]):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make billable model requests; otherwise force fallback")
    parser.add_argument("--cases", nargs="+", help="Fixture names; defaults to all")
    parser.add_argument("--output", type=Path, help="Save results and cited facts for manual review; never includes credentials")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
