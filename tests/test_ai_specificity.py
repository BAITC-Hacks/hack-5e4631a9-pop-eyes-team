"""Specificity is about source facts; it never supplies contractor rankings."""

import unittest

from ai_module.ranking import _ground_selection, _selection_schema
from ai_module.specificity import distinctive_evidence_ids


class SpecificityTests(unittest.TestCase):
    def test_concrete_facts_win_over_names_and_marketing(self):
        for text in ("Более 15 лет опыта.", "Педагог по актёрскому мастерству.",
                     "Специализируюсь на проведении деловых встреч.",
                     "• DJ и мультимедийное оборудование", "Вместимость до 200 гостей.",
                     "Без долгих речей.", "Работает на казахском, русском и английском языках."):
            facts = {"X:description:1": "Я, Икс, создаю незабываемый праздник.",
                     "X:description:2": text}
            with self.subTest(fact=text):
                self.assertEqual(distinctive_evidence_ids("X", facts), ["X:description:2"])

    def test_unknown_specialization_is_preserved_when_no_cue_matches(self):
        facts = {"X:description:1": "Создаёт бумажные скульптуры.",
                 "X:description:2": "Использует сухоцветы."}
        self.assertEqual(distinctive_evidence_ids("X", facts), list(facts))

    def test_empty_description_can_still_use_structured_fields(self):
        facts = {"X:field:event_formats": "корпоратив", "X:field:languages": "русский"}
        self.assertEqual(distinctive_evidence_ids("X", facts), list(facts))

    def test_same_fact_in_both_internal_roles_becomes_one_public_reference(self):
        facts = {"X:description:1": "Специализируется на корпоративных мероприятиях."}
        payload = {"selection_count": 1, "request": {"date": "2026-10-10"},
                   "candidates": [{"id": "X", "evidence": facts}]}
        schema = _selection_schema(payload)["properties"]["selected"]["items"]["anyOf"][0]["properties"]
        self.assertEqual(schema["supporting_evidence_ids"]["maxItems"], 0)
        raw = {"selected": [{"id": "X", "distinctive_evidence_id": "X:description:1",
                             "supporting_evidence_ids": ["X:description:1"]}]}
        item = _ground_selection(raw, payload)["selected"][0]
        self.assertEqual(item["evidence_ids"], ["X:description:1"])
        self.assertEqual(item["reason"].count("Специализируется"), 1)

    def test_schema_and_runtime_reject_generic_primary_but_keep_full_source(self):
        facts = {"X:description:1": "Каждый момент звучит правильно.",
                 "X:description:2": "Ведёт форумы на 500 человек.",
                 "X:description:3": "Без навязчивых конкурсов."}
        payload = {"selection_count": 1, "request": {"date": "2026-10-10"},
                   "candidates": [{"id": "X", "evidence": facts}]}
        schema = _selection_schema(payload)["properties"]["selected"]["items"]["anyOf"][0]["properties"]
        self.assertEqual(schema["distinctive_evidence_id"]["enum"], ["X:description:2", "X:description:3"])
        self.assertIn("X:description:3", schema["supporting_evidence_ids"]["items"]["enum"])
        self.assertNotIn("X:description:1", schema["supporting_evidence_ids"]["items"]["enum"])
        raw = {"selected": [{"id": "X", "distinctive_evidence_id": "X:description:1",
                             "supporting_evidence_ids": []}]}
        with self.assertRaises(ValueError):
            _ground_selection(raw, payload)
        raw["selected"][0].update(distinctive_evidence_id="X:description:2",
                                   supporting_evidence_ids=["X:description:3"])
        item = _ground_selection(raw, payload)["selected"][0]
        self.assertEqual(item["evidence_ids"], ["X:description:2", "X:description:3"])
        self.assertIn("Без навязчивых конкурсов", item["reason"])
        self.assertEqual(len(facts), 3)
        raw["selected"][0]["supporting_evidence_ids"] = ["X:description:1"]
        with self.assertRaises(ValueError):
            _ground_selection(raw, payload)


if __name__ == "__main__":
    unittest.main()
