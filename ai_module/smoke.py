"""Manual integration check; uses synthetic profiles unless --input is given."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from . import build_evidence, rank_candidates


def _synthetic_fixture():
    descriptions = [
        "Неформальные вечеринки, танцы и активные конкурсы.",
        "Деловые корпоративы, интеллигентный юмор и короткие выступления без конкурсов.",
        "Семейные праздники и интерактивные игры для гостей.",
        "Деловые встречи и корпоративы, короткие речи на русском и казахском языках.",
    ]
    candidates = [
        {"id": f"DEMO-{index:02}", "anon_name": f"Тестовый ведущий {index}",
         "city": "Алматы", "categories": ["Ведущий"], "price_from_kzt": index * 100000,
         "event_formats": ["корпоратив"], "languages": ["русский", "казахский"],
         "max_hours": 5.0, "description": description, "synthetic": True,
         "city_imputed": False, "price_imputed": False}
        for index, description in enumerate(descriptions, start=1)
    ]
    return {
        "request": {"city": "Алматы", "date": "2026-10-10", "event_type": "корпоратив",
                    "category": "Ведущий", "budget_kzt": 1000000, "duration_hours": None,
                    "language": None, "preferences": "Деловой корпоратив: интеллигентный юмор, без длинных речей и конкурсов"},
        "eligible_candidates": candidates,
    }


async def _run(args):
    if args.require_ai and not os.getenv("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY is missing; export it before running this check")
    fixture = json.loads(args.input.read_text(encoding="utf-8-sig")) if args.input else _synthetic_fixture()
    start = time.perf_counter()
    result = await rank_candidates(fixture["request"], fixture["eligible_candidates"])
    elapsed = time.perf_counter() - start
    profiles = {profile["id"]: profile for profile in fixture["eligible_candidates"]}
    for item in result["selected"]:
        facts = build_evidence(profiles[item["id"]])
        assert all(ref in facts for ref in item["evidence_ids"])
    print(json.dumps({
        "fixture": str(args.input) if args.input else "synthetic_demo_not_dataset",
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "elapsed_seconds": round(elapsed, 3),
        "eligible_count": len(profiles),
        "result": result,
    }, ensure_ascii=False, indent=2))
    if args.require_ai and result["selection_mode"] != "ai":
        raise SystemExit("AI check failed: received fallback; inspect the safe warning above")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON with request and eligible_candidates from backend")
    parser.add_argument("--require-ai", action="store_true", help="Fail if API selection was not successful")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
