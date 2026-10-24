import unittest
from datetime import datetime
from decimal import Decimal

from flights.domain.normalization import (
    canonical_currency,
    normalize_record,
    normalize_records,
    parse_datetime,
)


class NormalizationTests(unittest.TestCase):
    def test_normalizes_price_datetime_and_confirmed_currency(self):
        offer = normalize_record(
            {
                "offerId": "offer-1",
                "origin": "THR",
                "destination": "MHD",
                "departureDateTime": "2026-10-18T05:50:00",
                "arrivalDateTime": "2026-10-18T07:20:00",
                "adultPrice": "۵,۵۹۹,۰۰۰",
                "currency": "تومان",
            },
            source="local",
        )

        self.assertEqual(offer.price_amount, Decimal("5599000"))
        self.assertEqual(offer.currency, "IRT")
        self.assertEqual(offer.currency_status, "confirmed")
        self.assertEqual(offer.departure_at, datetime(2026, 10, 18, 5, 50))
        self.assertEqual(offer.arrival_at, datetime(2026, 10, 18, 7, 20))

    def test_canonicalizes_irr_irt_and_unknown_currency(self):
        self.assertEqual(canonical_currency("ریال"), ("IRR", "confirmed"))
        self.assertEqual(canonical_currency("rial"), ("IRR", "confirmed"))
        self.assertEqual(canonical_currency("تومان"), ("IRT", "confirmed"))
        self.assertEqual(canonical_currency("IRT"), ("IRT", "confirmed"))
        self.assertEqual(canonical_currency("واحد نامعلوم"), (None, "unknown"))
        self.assertEqual(canonical_currency(None), (None, "unknown"))

    def test_time_only_value_does_not_guess_a_date(self):
        self.assertIsNone(parse_datetime("07:20"))
        offer = normalize_record(
            {"departureDateTime": "2026-10-18T05:50:00", "arrivalTime": "07:20"},
            source="local",
        )
        self.assertIsNone(offer.arrival_at)

    def test_uses_explicit_source_id_and_generates_stable_id_otherwise(self):
        explicit = normalize_record({"offerId": "offer-1"}, source="local")
        self.assertEqual(explicit.offer_id, "offer-1")

        record = {"systemKey": "source-key", "airline": "Example", "adultPrice": "10"}
        generated_a = normalize_record(record, source="local")
        generated_b = normalize_record(record, source="local")
        self.assertTrue(generated_a.offer_id.startswith("local:generated-"))
        self.assertEqual(generated_a.offer_id, generated_b.offer_id)
        self.assertNotEqual(generated_a.offer_id, "source-key")

    def test_missing_fields_are_none_and_unknown_currency_is_not_confirmed(self):
        offer = normalize_record({"airline": "Example"}, source="local")

        self.assertEqual(offer.airline, "Example")
        self.assertIsNone(offer.origin)
        self.assertIsNone(offer.destination)
        self.assertIsNone(offer.price_amount)
        self.assertIsNone(offer.currency)
        self.assertEqual(offer.currency_status, "unknown")
        self.assertIsNone(offer.departure_at)
        self.assertIsNone(offer.arrival_at)

    def test_invalid_record_is_reported_without_aborting_batch(self):
        offers, issues = normalize_records(
            [
                {"offerId": "valid", "adultPrice": "100", "currency": "ریال"},
                "not-a-record",
                {"offerId": "also-valid", "adultPrice": "200", "currency": "تومان"},
            ],
            source="local",
        )

        self.assertEqual([offer.offer_id for offer in offers], ["valid", "also-valid"])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].index, 1)

    def test_invalid_source_is_reported_as_record_issue(self):
        offers, issues = normalize_records([{"offerId": "x"}], source="")

        self.assertEqual(offers, [])
        self.assertEqual(len(issues), 1)
        self.assertIn("source must not be empty", issues[0].message)


if __name__ == "__main__":
    unittest.main()
