import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from flights.data.loader import DataLoadError, load_flight_offers, load_json_records


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "data" / "sample_flights.json"


class DataLoaderTests(unittest.TestCase):
    def test_project_fixture_loads_and_normalizes_valid_records(self):
        offers, issues = load_flight_offers(
            FIXTURE_PATH,
            observed_at=datetime(2026, 10, 18, 10, 0),
        )

        self.assertEqual(len(offers), 10)
        self.assertEqual(len(issues), 0)
        self.assertEqual(offers[0].offer_id, "fixture-thr-mhd-001")
        self.assertEqual(offers[0].currency, "IRT")
        self.assertEqual(offers[1].currency, "IRR")
        self.assertIsNone(offers[2].arrival_at)
        self.assertEqual(offers[3].origin, "THR")
        self.assertIsNone(offers[4].flight_type)
        self.assertEqual(offers[5].departure_at.date().isoformat(), "2026-10-27")
        self.assertEqual(offers[8].departure_at.date().isoformat(), "2026-10-30")
        self.assertEqual(offers[9].departure_at.date().isoformat(), "2026-11-02")
        self.assertEqual(offers[0].observed_at, datetime(2026, 10, 18, 10, 0))

    def test_loader_path_is_not_relative_to_current_working_directory(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary_directory:
            try:
                os.chdir(temporary_directory)
                records = load_json_records(FIXTURE_PATH)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(len(records), 10)

    def test_missing_file_raises_clear_error(self):
        with self.assertRaisesRegex(DataLoadError, "fixture file not found"):
            load_json_records(FIXTURE_PATH.parent / "does-not-exist.json")

    def test_invalid_json_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.json"
            path.write_text("{not valid json", encoding="utf-8")

            with self.assertRaisesRegex(DataLoadError, "invalid fixture JSON"):
                load_json_records(path)

    def test_invalid_envelope_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "wrong-shape.json"
            path.write_text(json.dumps({"result": {}}), encoding="utf-8")

            with self.assertRaisesRegex(DataLoadError, "offers"):
                load_json_records(path)


if __name__ == "__main__":
    unittest.main()
