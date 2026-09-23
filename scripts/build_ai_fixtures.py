"""Build evaluation fixtures from the supplied CSV, never import production data.

Run from the repository root: python scripts/build_ai_fixtures.py [--check]
The backend remains the sole owner of production filtering and SQL import.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "hackathon dataset anonymized .csv"
SOURCE = ROOT / SOURCE_NAME
if not SOURCE.exists():
    SOURCE = ROOT / "data/contractors.csv"  # Docker's copy of the same source.
DESTINATION = ROOT / "tests/fixtures/ai"
SOURCE_SHA256 = "87d082de8481f63795ba9d5b9509b5ffbdeabe3f99efd28b114be780df35d422"

# Counts and fallback IDs come from DATA_AUDIT.md, not model predictions.
SCENARIOS = [
    ("hosts_business", "Алматы", "Ведущий", "2026-10-10", 1000000, 4,
     ["HK-88430", "HK-29829", "HK-27222"],
     "Деловой корпоратив: в первую очередь опыт деловых мероприятий и интеллигентный юмор. Без навязчивых конкурсов.",
     {"first_in": ["HK-88430", "HK-77838", "HK-27222"],
      "prefer_before": [["HK-88430", "HK-29829"], ["HK-77838", "HK-29829"], ["HK-27222", "HK-29829"]]}),
    ("hosts_party", "Алматы", "Ведущий", "2026-10-10", 1000000, 4,
     ["HK-88430", "HK-29829", "HK-27222"],
     "Неформальный корпоратив: главный акцент на развлечениях и танцах, без долгих речей и наставлений.",
     {"first_in": ["HK-29829"]}),
    ("hosts_neutral", "Алматы", "Ведущий", "2026-10-10", 1000000, 4,
     ["HK-88430", "HK-29829", "HK-27222"], "", {}),
    ("hosts_november", "Алматы", "Ведущий", "2026-11-14", 1000000, 4,
     ["HK-44923", "HK-29829", "HK-27222"], "Корпоратив с юмором и вниманием к гостям.", {}),
    ("hosts_december", "Алматы", "Ведущий", "2026-12-19", 1000000, 1,
     ["HK-35215"], "Корпоратив с тонким юмором и персональным подходом.", {}),
    ("florist", "Алматы", "Флорист", "2026-10-10", 500000, 1,
     ["HK-39372"], "Нужно авторское цветочное оформление корпоративного мероприятия.", {}),
    ("venues", "Алматы", "Банкетный зал", "2026-11-14", 6000000, 2,
     ["HK-64395", "HK-90011"],
     "Корпоратив примерно на 180 гостей. В приоритете подтверждённая вместимость, свой кейтеринг и парковка.",
     {"first_in": ["HK-90011"]}),
    ("low_budget", "Алматы", "Ведущий", "2026-10-10", 10000, 0, [], "", {}),
    ("category_absent", "Астана", "Декоратор", "2026-10-10", 1000000, 0, [], "", {}),
]


def build():
    # Git checkouts may use LF or CRLF. This fixture checksum normalizes only
    # newlines; it is distinct from the backend's raw-file source checksum.
    digest = hashlib.sha256(SOURCE.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Source CSV changed: recalculate audited counts before rebuilding fixtures")
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        profiles = list(csv.DictReader(stream))
    for profile in profiles:
        for field in ("categories", "event_formats", "languages", "busy_dates"):
            profile[field] = [value for value in profile[field].split("|") if value]
        for field in ("synthetic", "city_imputed", "price_imputed"):
            profile[field] = profile[field] == "True"
        profile["price_from_kzt"] = int(profile["price_from_kzt"])
        profile["max_hours"] = float(profile["max_hours"]) if profile["max_hours"] else None
    if len(profiles) != 66 or len({p["id"] for p in profiles}) != 66:
        raise ValueError("Expected 66 unique profiles")

    fixtures = {}
    for name, city, category, day, budget, count, fallback_ids, preferences, quality in SCENARIOS:
        in_category = [p for p in profiles if p["city"] == city and category in p["categories"]]
        eligible = [p for p in in_category if day not in p["busy_dates"]
                    and p["price_from_kzt"] <= budget and "корпоратив" in p["event_formats"]]
        actual_fallback = [p["id"] for p in sorted(eligible, key=lambda p: (p["price_from_kzt"], p["id"]))[:3]]
        if len(eligible) != count or actual_fallback != fallback_ids:
            raise ValueError(f"Audit mismatch: {name}")
        fixtures[name] = {
            "_meta": {
                "source": SOURCE_NAME, "source_sha256_lf": digest,
                "expected_status": "category_absent" if not in_category else "matched" if eligible else "no_matches",
                "expected_eligible_count": count, "expected_fallback_ids": fallback_ids,
                "quality_checks": quality,
            },
            "request": {
                "city": city, "date": day, "event_type": "корпоратив", "category": category,
                "budget_kzt": budget, "duration_hours": None, "language": None, "preferences": preferences,
            },
            "eligible_candidates": [
                {field: value for field, value in profile.items() if field != "busy_dates"}
                for profile in sorted(eligible, key=lambda p: p["id"])
            ],
        }
    return fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check existing fixtures without writing")
    args = parser.parse_args()
    for name, fixture in build().items():
        path = DESTINATION / f"{name}.json"
        rendered = json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"Fixture out of date: {path.name}")
        else:
            DESTINATION.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"{name}: {len(fixture['eligible_candidates'])} eligible")


if __name__ == "__main__":
    main()
