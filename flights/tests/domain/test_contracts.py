import unittest
from datetime import date

from flights.domain.contracts import FlightSearch


class FlightSearchTests(unittest.TestCase):
    def test_defaults_are_applied(self):
        search = FlightSearch(
            origin="THR",
            destination="MHD",
            departure_date=date(2026, 10, 18),
        )

        self.assertEqual(search.passengers, 1)
        self.assertEqual(search.trip_type, "one_way")
        self.assertIsNone(search.return_date)

    def test_valid_round_trip_requires_and_accepts_return_date(self):
        search = FlightSearch(
            origin="THR",
            destination="MHD",
            departure_date=date(2026, 10, 18),
            trip_type="round_trip",
            return_date=date(2026, 10, 20),
            passengers=2,
        )

        self.assertEqual(search.trip_type, "round_trip")
        self.assertEqual(search.passengers, 2)

    def test_rejects_invalid_values(self):
        cases = [
            dict(origin="", destination="MHD"),
            dict(origin="THR", destination=""),
            dict(origin="THR", destination="MHD", passengers=0),
            dict(origin="THR", destination="MHD", trip_type="invalid"),
            dict(origin="THR", destination="MHD", trip_type="round_trip"),
            dict(
                origin="THR",
                destination="MHD",
                departure_date=date(2026, 10, 20),
                return_date=date(2026, 10, 19),
            ),
        ]

        for kwargs in cases:
            kwargs.setdefault("departure_date", date(2026, 10, 18))
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    FlightSearch(**kwargs)

