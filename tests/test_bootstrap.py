"""Integration checks against the running app, DB and original CSV.

Run: docker compose exec app python -m unittest discover -s tests -v
"""

import csv
import hashlib
import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from app.db import connect


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv_path = Path("/app/data/contractors.csv")
        with cls.csv_path.open(encoding="utf-8-sig", newline="") as source:
            cls.source_rows = list(csv.DictReader(source))

    def get_json(self, path):
        with urlopen("http://127.0.0.1:8000" + path, timeout=10) as response:
            return json.load(response)

    def test_every_csv_field_survives_import(self):
        with connect() as connection:
            records = connection.execute("SELECT * FROM contractors").fetchall()
        by_id = {row["id"]: row for row in records}
        self.assertEqual(len(records), 66)
        self.assertEqual(set(by_id), {row["id"] for row in self.source_rows})
        for source in self.source_rows:
            with self.subTest(contractor_id=source["id"]):
                expected = dict(source)
                for field in ("categories", "event_formats", "languages"):
                    expected[field] = source[field].split("|")
                for field in ("city_imputed", "synthetic", "price_imputed"):
                    expected[field] = source[field] == "True"
                expected["price_from_kzt"] = int(source["price_from_kzt"])
                expected["max_hours"] = Decimal(source["max_hours"]) if source["max_hours"] else None
                expected["busy_dates"] = [date.fromisoformat(value) for value in source["busy_dates"].split("|") if value]
                self.assertEqual(by_id[source["id"]], expected)

    def test_metadata_matches_source_file_and_calendar(self):
        with connect() as connection:
            metadata = connection.execute("SELECT * FROM dataset_metadata").fetchone()
        self.assertEqual(metadata["source_sha256"], hashlib.sha256(self.csv_path.read_bytes()).hexdigest())
        self.assertEqual(metadata["profile_count"], 66)
        self.assertEqual(metadata["calendar_start"], date(2026, 9, 23))
        self.assertEqual(metadata["calendar_end"], date(2026, 12, 31))

    def test_health_reports_seeded_database(self):
        health = self.get_json("/health")
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["database"], "ok")
        self.assertEqual(health["profiles_count"], 66)
        self.assertEqual(len(health["dataset_version"]), 64)

    def test_options_are_complete(self):
        options = self.get_json("/api/options")
        self.assertEqual(set(options["cities"]), {row["city"] for row in self.source_rows})
        for response_field, source_field in (("categories", "categories"), ("event_types", "event_formats"), ("languages", "languages")):
            expected = {value for row in self.source_rows for value in row[source_field].split("|")}
            self.assertEqual(set(options[response_field]), expected)
        self.assertEqual(options["calendar_window"], {"start": "2026-09-23", "end": "2026-12-31"})

    def test_profile_preserves_null_and_flags(self):
        profile = self.get_json("/api/contractors/HK-39372")
        self.assertIsNone(profile["max_hours"])
        self.assertIs(profile["price_imputed"], True)
        self.assertIs(profile["synthetic"], False)
        self.assertEqual(profile["price_from_kzt"], 200000)
        self.assertIn("2026-09-25", profile["busy_dates"])

    def test_unknown_profile_returns_404(self):
        with self.assertRaises(HTTPError) as failure:
            self.get_json("/api/contractors/DOES-NOT-EXIST")
        self.assertEqual(failure.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
