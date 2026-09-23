"""Business rules and real HTTP/DB integration, without any external AI calls."""

import asyncio
import copy
import json
import os
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.catalog import load_catalog
from app.ranking import build_evidence, select_candidates
from app.recommendations import filter_candidates, recommend, request_key, save_response
from app.schemas import RecommendationRequest


BASE_REQUEST = {
    "city": "Алматы", "date": "2026-10-10", "event_type": "корпоратив", "category": "Ведущий",
    "budget_kzt": 1000000, "duration_hours": None, "language": None, "preferences": "Деловой корпоратив",
}


class FilteringTests(unittest.TestCase):
    def test_inclusive_limits_null_duration_and_first_exclusion_reason(self):
        request = dict(BASE_REQUEST, budget_kzt=100, duration_hours=4, language="русский")
        base = {"id": "a", "city": "Алматы", "categories": ["Ведущий"], "price_from_kzt": 100,
                "max_hours": 4, "languages": ["русский"], "event_formats": ["корпоратив"], "busy_dates": []}
        rows = [base, dict(base, id="b", max_hours=None),
                dict(base, id="c", busy_dates=[request["date"]], price_from_kzt=101),
                dict(base, id="d", price_from_kzt=101, languages=[]),
                dict(base, id="e", event_formats=["свадьба"]),
                dict(base, id="f", max_hours=3.5), dict(base, id="g", languages=["казахский"]),
                dict(base, id="other-city", city="Астана"), dict(base, id="other-category", categories=["Флорист"])]
        total, eligible, excluded = filter_candidates(request, rows)
        self.assertEqual(total, 7)
        self.assertEqual([c["id"] for c in eligible], ["a", "b"])
        self.assertEqual(excluded, dict.fromkeys(("date", "budget", "event_type", "duration", "language"), 1))

    def test_cache_key_accounts_for_preferences_date_data_and_ranking(self):
        key = request_key(BASE_REQUEST, "data-v1", "ranking-v1")
        for request, data, ranking in (
            (dict(BASE_REQUEST, date="2026-12-19"), "data-v1", "ranking-v1"),
            (dict(BASE_REQUEST, preferences="Танцы"), "data-v1", "ranking-v1"),
            (BASE_REQUEST, "data-v2", "ranking-v1"), (BASE_REQUEST, "data-v1", "ranking-v2"),
        ):
            self.assertNotEqual(key, request_key(request, data, ranking))


class AIContractTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata, cls.catalog = load_catalog()
        _, cls.eligible, _ = filter_candidates(BASE_REQUEST, cls.catalog)

    async def test_all_four_real_candidates_reach_ai_and_order_is_preserved(self):
        self.assertEqual(len(self.eligible), 4)
        chosen = list(reversed(self.eligible))[:3]

        async def rank(request, candidates):
            self.assertEqual(request["preferences"], BASE_REQUEST["preferences"])
            self.assertEqual({c["id"] for c in candidates}, {c["id"] for c in self.eligible})
            self.assertEqual(len(candidates), 4)
            for c in candidates:
                self.assertIsInstance(c["price_from_kzt"], int)
                self.assertIsInstance(c["categories"], list)
                self.assertEqual(c["name"], c["anon_name"])
                self.assertEqual(c["evidence"], build_evidence(c))
            # Mutating module input must not change the canonical DB-backed cards.
            candidates[0]["anon_name"] = "Invented name"
            return {"selection_mode": "ai", "selected": [
                {"id": c["id"], "reason": f"Факт: {c['description'][:80]}",
                 "evidence_ids": [f"{c['id']}:description:1"]} for c in chosen]}

        with patch.dict(os.environ, {"AI_MODULE": "test_ranker", "AI_MODE": "auto"}), \
             patch.dict(sys.modules, {"test_ranker": SimpleNamespace(rank_candidates=rank)}), \
             patch("app.recommendations.cached_response", return_value=None), \
             patch("app.recommendations.save_response", side_effect=lambda key, payload, response: response):
            result = await recommend(RecommendationRequest(**BASE_REQUEST))
        self.assertEqual(result["selection_mode"], "ai")
        self.assertEqual([c["id"] for c in result["cards"]], [c["id"] for c in chosen])
        self.assertEqual([c["name"] for c in result["cards"]], [c["anon_name"] for c in chosen])

    async def test_bad_ai_outputs_fall_back_to_real_eligible_candidates(self):
        valid = {"selection_mode": "ai", "selected": [
            {"id": c["id"], "reason": "Факт из профиля", "evidence_ids": [f"{c['id']}:description:1"]}
            for c in self.eligible[:3]]}
        unknown, duplicate, foreign_fact, blank_reason, bad_mode = [copy.deepcopy(valid) for _ in range(5)]
        unknown["selected"][0]["id"] = "DEMO-1"
        duplicate["selected"][1] = duplicate["selected"][0]
        foreign_fact["selected"][0]["evidence_ids"] = valid["selected"][1]["evidence_ids"]
        blank_reason["selected"][0]["reason"] = " "
        bad_mode["selection_mode"] = "pretend-ai"
        for raw in (unknown, duplicate, foreign_fact, blank_reason, bad_mode,
                    dict(valid, selected=valid["selected"][:2]), {"nonsense": True}):
            with self.subTest(raw=raw):
                async def rank(request, candidates):
                    return raw
                with patch.dict(os.environ, {"AI_MODULE": "test_ranker", "AI_MODE": "auto"}), \
                     patch.dict(sys.modules, {"test_ranker": SimpleNamespace(rank_candidates=rank)}):
                    result = await select_candidates(BASE_REQUEST, self.eligible)
                self.assertEqual(result.selection_mode, "fallback")
                self.assertEqual(len(result.selected), 3)
                self.assertTrue({c.id for c in result.selected} <= {c["id"] for c in self.eligible})

    async def test_timeout_and_missing_module_are_honest_fallback(self):
        async def rank(request, candidates):
            await asyncio.sleep(1)
            raise AssertionError("Should have timed out")
        with patch.dict(os.environ, {"AI_MODULE": "test_ranker", "AI_MODE": "auto", "AI_TIMEOUT_SECONDS": "0.01"}), \
             patch.dict(sys.modules, {"test_ranker": SimpleNamespace(rank_candidates=rank)}):
            result = await select_candidates(BASE_REQUEST, self.eligible)
        self.assertEqual(result.selection_mode, "fallback")
        with patch.dict(os.environ, {"AI_MODULE": ""}):
            result = await select_candidates(BASE_REQUEST, self.eligible)
        self.assertEqual(result.selection_mode, "fallback")

    async def test_empty_result_never_calls_ranking(self):
        with patch("app.recommendations.cached_response", return_value=None), \
             patch("app.recommendations.save_response", side_effect=lambda key, payload, response: response), \
             patch("app.recommendations.select_candidates", side_effect=AssertionError("No eligible candidates")):
            result = await recommend(RecommendationRequest(**dict(BASE_REQUEST, budget_kzt=1)))
        self.assertEqual(result["status"], "no_matches")
        self.assertEqual(result["cards"], [])
        self.assertIsNone(result["selection_mode"])


class RecommendationHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata, cls.catalog = load_catalog()
        cls.by_id = {c["id"]: c for c in cls.catalog}

    def post(self, request):
        req = Request("http://127.0.0.1:8000/api/recommendations", data=json.dumps(request).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    def test_real_scenarios_and_complete_card_contract(self):
        scenarios = [({}, "matched", 10, 4, 3),
                     ({"date": "2026-12-19"}, "matched", 10, 1, 1),
                     ({"category": "Флорист", "budget_kzt": 500000}, "matched", 2, 1, 1),
                     ({"budget_kzt": 10000}, "no_matches", 10, 0, 0),
                     ({"city": "Астана", "category": "Декоратор"}, "category_absent", 0, 0, 0),
                     ({"category": "Банкетный зал", "date": "2026-11-14", "budget_kzt": 6000000}, "matched", 7, 2, 2)]
        for overrides, status, total, eligible, count in scenarios:
            with self.subTest(overrides=overrides):
                request = dict(BASE_REQUEST, **overrides)
                response = self.post(request)
                self.assertEqual(response["status"], status)
                self.assertEqual(response["total_in_city_category"], total)
                self.assertEqual(response["eligible_count"], eligible)
                self.assertEqual(len(response["cards"]), count)
                self.assertEqual(sum(response["excluded_counts"].values()) + eligible, total)
                self.assertEqual(response["dataset_version"], self.metadata["dataset_version"])
                self.assertTrue(response["recommendation_version"])
                self.assertIsInstance(response["cache_hit"], bool)
                if not count:
                    self.assertIsNone(response["selection_mode"])
                for card in response["cards"]:
                    db = self.by_id[card["id"]]
                    self.assertEqual(card["name"], db["anon_name"])
                    self.assertNotIn("anon_name", card)
                    for field in ("categories", "city", "price_from_kzt", "synthetic", "city_imputed", "price_imputed"):
                        self.assertEqual(card[field], db[field])
                    self.assertLessEqual(card["price_from_kzt"], request["budget_kzt"])
                    self.assertNotIn(request["date"], db["busy_dates"])
                    self.assertTrue(card["reason"])
                    self.assertTrue(card["evidence_ids"])

    def test_repeat_and_concurrent_requests_return_one_saved_result(self):
        request = dict(BASE_REQUEST, preferences="Integration test " + uuid.uuid4().hex)
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(self.post, [request] * 4))
        self.assertEqual(sum(not r["cache_hit"] for r in responses), 1)
        normalized = [{k: v for k, v in r.items() if k != "cache_hit"} for r in responses]
        self.assertTrue(all(r == normalized[0] for r in normalized))
        self.assertTrue(self.post(request)["cache_hit"])

    def test_concurrent_different_decisions_preserve_first_committed_response(self):
        payload = dict(BASE_REQUEST, preferences="Race test " + uuid.uuid4().hex)
        response = self.post(payload)
        key = request_key(payload, response["dataset_version"], "race-" + uuid.uuid4().hex)
        alternatives = [dict(response, message=f"Decision {i}") for i in range(4)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            saved = list(pool.map(lambda candidate: save_response(key, payload, candidate), alternatives))
        self.assertEqual(len({r["message"] for r in saved}), 1)
        self.assertEqual(sum(not r["cache_hit"] for r in saved), 1)

    def test_invalid_input_returns_field_errors(self):
        for changes, field in [({"date": "2027-01-01"}, "date"), ({"city": "Unknown"}, "city"),
                               ({"category": "Unknown"}, "category"), ({"language": "Unknown"}, "language"),
                               ({"event_type": "Unknown"}, "event_type"), ({"budget_kzt": 0}, "budget_kzt"),
                               ({"budget_kzt": True}, "budget_kzt"), ({"budget_kzt": 10.5}, "budget_kzt"),
                               ({"duration_hours": -1}, "duration_hours"), ({"preferences": "x" * 1001}, "preferences")]:
            with self.subTest(changes=changes), self.assertRaises(HTTPError) as failure:
                self.post(dict(BASE_REQUEST, **changes))
            self.assertEqual(failure.exception.code, 422)
            error = json.load(failure.exception)
            self.assertIn(field, [entry["loc"][1] for entry in error["detail"]])

    def test_frontend_assets_and_swagger_are_served_on_same_origin(self):
        for path, content_type in (("/", "text/html"), ("/app.js", "javascript"), ("/styles.css", "text/css"), ("/docs", "text/html")):
            with urlopen("http://127.0.0.1:8000" + path, timeout=10) as response:
                self.assertIn(content_type, response.headers["Content-Type"])
                content = response.read().decode()
                self.assertNotIn("DEMO-1", content)
                self.assertNotIn("demo-scenario", content)
