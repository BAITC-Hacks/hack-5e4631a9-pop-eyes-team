"""Regressions for specific, displayed source facts rather than generic praise."""

import json
import unittest

from ai_module import build_evidence
from ai_module.evaluate import EXPLANATION_RUBRIC, FIXTURE_DIR, check_result


class ExplanationQualityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((FIXTURE_DIR / "hosts_business.json").read_text(encoding="utf-8"))
        self.profiles = {p["id"]: p for p in self.fixture["eligible_candidates"]}
        self.facts = {cid: build_evidence(p) for cid, p in self.profiles.items()}
        self.ids = ["HK-27222", "HK-77838", "HK-88430"]

    def result_for(self, phrases):
        # Public responses as stored by v6, including answers v7 now rejects.
        selected = []
        for cid, phrase in zip(self.ids, phrases):
            ref, text = next((ref, text) for ref, text in self.facts[cid].items()
                             if phrase in text.casefold() and ":description:" in ref)
            quote = text.strip().rstrip(".!?…")
            selected.append({"id": cid, "evidence_ids": [ref],
                             "reason": f"Свободен по календарю на 10.10.2026. В профиле: «{quote}»."})
        return {"selection_mode": "ai", "selected": selected}

    def test_generic_v6_style_is_detected_despite_valid_sources_and_length(self):
        result = self.result_for(["европейская подача", "каждый момент", "интеллигентного юмора"])
        errors = check_result(self.fixture, result, live=True)
        self.assertEqual(set(errors), {f"missing_distinctive_fact:{cid}" for cid in self.ids})

    def test_distinct_experience_facts_pass_without_changing_order_or_contract(self):
        result = self.result_for(["12 лет", "актёр театра", "деловых встреч"])
        self.assertEqual(check_result(self.fixture, result, live=True), [])
        self.assertEqual([item["id"] for item in result["selected"]], self.ids)
        self.assertTrue(all(len(item["reason"]) <= 280 for item in result["selected"]))

    def test_concrete_reference_without_displayed_quote_does_not_pass(self):
        result = self.result_for(["12 лет", "актёр театра", "деловых встреч"])
        item = result["selected"][1]
        item["reason"] = "Свободен по календарю на 10.10.2026. Отличный выбор для вашего мероприятия."
        errors = check_result(self.fixture, result, live=True)
        self.assertIn("missing_distinctive_fact:HK-77838", errors)
        self.assertTrue(any(e.startswith("cited_fact_not_displayed:HK-77838:") for e in errors))

    def test_invented_concrete_text_cannot_earn_credit_with_generic_reference(self):
        result = self.result_for(["12 лет", "каждый момент", "деловых встреч"])
        result["selected"][1]["reason"] = "Свободен по календарю на 10.10.2026. В профиле: «Актёр театра и кино»."
        self.assertIn("missing_distinctive_fact:HK-77838", check_result(self.fixture, result, live=True))

    def test_all_rubric_profiles_have_real_complete_facts_within_quote_budget(self):
        profiles = {}
        for path in FIXTURE_DIR.glob("*.json"):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            profiles.update({p["id"]: p for p in fixture["eligible_candidates"]})
        self.assertEqual(set(profiles), set(EXPLANATION_RUBRIC["profiles"]))
        for cid, alternatives in EXPLANATION_RUBRIC["profiles"].items():
            quotes = [text.casefold() for ref, text in build_evidence(profiles[cid]).items()
                      if ":description:" in ref and len(text) <= 200]
            with self.subTest(candidate=cid):
                self.assertTrue(any(all(term in quote for term in terms)
                                    for terms in alternatives for quote in quotes))


if __name__ == "__main__":
    unittest.main()
