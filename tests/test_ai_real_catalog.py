"""Offline evaluation of the actual catalog, independent of Docker/backend."""

import csv
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_module import build_evidence, normalize_candidate, rank_candidates
from ai_module.evaluate import check_result, FIXTURE_DIR
from scripts.build_ai_fixtures import build, SOURCE


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    def test_fixture_checksum_is_portable_between_windows_and_linux(self):
        expected = build()
        source = SOURCE.read_bytes().replace(b"\r\n", b"\n")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.csv"
            for contents in (source, source.replace(b"\n", b"\r\n")):
                path.write_bytes(contents)
                with patch("scripts.build_ai_fixtures.SOURCE", path):
                    self.assertEqual(build(), expected)

    def test_fixtures_reproduce_source_and_audited_counts(self):
        fixtures = build()
        self.assertEqual(len(fixtures), 9)
        for name, expected in fixtures.items():
            actual = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
            self.assertEqual(actual, expected)

    def test_all_66_profiles_accept_sql_types_and_json_types_identically(self):
        with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
            profiles = list(csv.DictReader(stream))
        for profile in profiles:
            for field in ("categories", "event_formats", "languages"):
                profile[field] = profile[field].split("|")
            for field in ("synthetic", "city_imputed", "price_imputed"):
                profile[field] = profile[field] == "True"
            profile["price_from_kzt"] = int(profile["price_from_kzt"])
            profile["max_hours"] = Decimal(profile["max_hours"]) if profile["max_hours"] else None
            normalized = normalize_candidate(profile)
            with self.subTest(candidate_id=profile["id"]):
                self.assertEqual(build_evidence(profile), build_evidence(json.loads(json.dumps(normalized))))
                fragments = [text for ref, text in build_evidence(profile).items() if ":description:" in ref]
                self.assertEqual(" ".join(fragments), " ".join(profile["description"].split()))
                self.assertTrue(all(len(fragment) <= 180 for fragment in fragments))
        self.assertEqual(len(profiles), 66)

    async def test_all_nine_cases_have_audited_fallback_order_and_valid_facts(self):
        for name, fixture in build().items():
            with self.subTest(name=name), patch.dict(os.environ, {"AI_MODE": "fallback"}):
                result = await rank_candidates(fixture["request"], fixture["eligible_candidates"])
            self.assertEqual(check_result(fixture, result, live=False), [])

    def test_quality_rubric_detects_business_misranking(self):
        fixture = build()["hosts_business"]
        # The baseline model incorrectly put the party specialist above a host
        # with explicitly intelligent, unobtrusive presentation.
        result = {"selection_mode": "ai", "selected": [
            {"id": candidate_id, "reason": "Объяснение", "evidence_ids": [f"{candidate_id}:description:1"]}
            for candidate_id in ("HK-88430", "HK-29829", "HK-77838")
        ]}
        errors = check_result(fixture, result, live=True)
        self.assertTrue(any(error.startswith("context_priority:") for error in errors))


if __name__ == "__main__":
    unittest.main()
