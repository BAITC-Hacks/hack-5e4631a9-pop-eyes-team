"""Backend + real AI-module boundary; no database or network required."""

import json
import os
import unittest
from unittest.mock import patch

import ai_module
from ai_module import ranking
from ai_module.evaluate import FIXTURE_DIR
from app.ranking import select_candidates
from app.recommendations import filter_candidates, recommendation_version, request_key


class AIIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_accepts_short_dated_reasons_with_shared_facts(self):
        fixture = json.loads((FIXTURE_DIR / "hosts_party.json").read_text(encoding="utf-8"))
        profiles = [dict(c, busy_dates=[]) for c in fixture["eligible_candidates"]]
        chosen = ["HK-29829", "HK-27222", "HK-88430"]

        async def provider(payload, **kwargs):
            self.assertEqual(len(payload["candidates"]), 4)
            self.assertEqual(payload["request"]["preferences"], fixture["request"]["preferences"])
            return ranking._ground_selection({"selected": [
                {"id": cid, "distinctive_evidence_id": f"{cid}:description:{number}", "supporting_evidence_ids": []}
                for cid, number in zip(chosen, [1, 1, 3])
            ]}, payload)

        with patch.dict(os.environ, {"AI_MODULE": "ai_module", "AI_MODE": "auto", "OPENAI_API_KEY": "test-key"}), \
             patch.object(ranking, "_call_model", provider):
            result = await select_candidates(fixture["request"], profiles)
        self.assertEqual(result.selection_mode, "ai")
        self.assertEqual([item.id for item in result.selected], chosen)
        for item in result.selected:
            self.assertIn("10.10.2026", item.reason)
            self.assertLessEqual(len(item.reason), 280)
            profile = next(c for c in profiles if c["id"] == item.id)
            self.assertTrue(set(item.evidence_ids) <= ai_module.build_evidence(profile).keys())

    async def test_filter_removes_busy_candidate_before_date_is_used_in_reason(self):
        fixture = json.loads((FIXTURE_DIR / "hosts_party.json").read_text(encoding="utf-8"))
        profiles = [dict(c, busy_dates=[]) for c in fixture["eligible_candidates"]]
        profiles[0]["busy_dates"] = [fixture["request"]["date"]]
        _, eligible, excluded = filter_candidates(fixture["request"], profiles)
        self.assertEqual(excluded["date"], 1)
        with patch.dict(os.environ, {"AI_MODULE": "ai_module", "AI_MODE": "auto", "OPENAI_API_KEY": ""}):
            result = await select_candidates(fixture["request"], eligible)
        self.assertEqual(result.selection_mode, "fallback")
        self.assertNotIn(profiles[0]["id"], [item.id for item in result.selected])
        for item in result.selected:
            self.assertIn("10.10.2026", item.reason)
            self.assertEqual(len(item.evidence_ids), 2)

    def test_new_ai_implementation_invalidates_cache_even_with_unchanged_env(self):
        with patch.dict(os.environ, {"AI_MODULE": "ai_module", "AI_VERSION": "unchanged"}):
            with patch.object(ai_module, "RECOMMENDATION_VERSION", "old"):
                previous = recommendation_version()
            with patch.object(ai_module, "RECOMMENDATION_VERSION", "new"):
                current = recommendation_version()
        self.assertNotEqual(previous, current)
        self.assertNotEqual(request_key({}, "dataset-v1", previous), request_key({}, "dataset-v1", current))

    def test_unavailable_optional_module_does_not_break_versioning(self):
        with patch.dict(os.environ, {"AI_MODULE": "module_that_does_not_exist"}):
            self.assertEqual(recommendation_version(), recommendation_version())


if __name__ == "__main__":
    unittest.main()
