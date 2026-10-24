import unittest
from datetime import datetime, timezone
from decimal import Decimal

from flights.services.presentation import (
    duration_minutes,
    format_datetime,
    format_price,
    format_price_with_currency,
    present_ranked_flight,
    safe_source_url,
    translate_reason,
    translate_warning,
)
from flights.domain.contracts import FlightOffer
from flights.services.ranking import RankedFlight


class PresentationTests(unittest.TestCase):
    def test_duration_handles_aware_datetimes_without_timezone_guessing(self):
        departure = datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc)
        arrival = datetime(2026, 10, 21, 0, 30, tzinfo=timezone.utc)

        self.assertEqual(duration_minutes(departure, arrival), Decimal("60"))

    def test_mixed_naive_and_aware_duration_is_unknown(self):
        departure = datetime(2026, 10, 20, 23, 30)
        arrival = datetime(2026, 10, 21, 0, 30, tzinfo=timezone.utc)

        self.assertIsNone(duration_minutes(departure, arrival))

    def test_only_http_and_https_source_urls_are_clickable(self):
        self.assertEqual(safe_source_url("https://example.test/flight"), "https://example.test/flight")
        self.assertIsNone(safe_source_url("javascript:alert(1)"))
        self.assertIsNone(safe_source_url("/relative/path"))

    def test_price_is_formatted_without_changing_its_value(self):
        self.assertEqual(format_price(Decimal("5599000")), "5,599,000")
        self.assertIsNone(format_price(None))

    def test_price_display_uses_known_currency_name(self):
        self.assertEqual(
            format_price_with_currency(Decimal("2500000"), "IRT", "confirmed"),
            "2,500,000 تومان",
        )
        self.assertEqual(
            format_price_with_currency(Decimal("120"), "USD", "confirmed"),
            "120 دلار آمریکا",
        )

    def test_unknown_currency_is_explicit_and_not_guessed(self):
        self.assertEqual(
            format_price_with_currency(Decimal("100"), None, "unknown"),
            "100 واحد پول نامشخص",
        )

    def test_missing_price_is_simple_and_does_not_claim_currency(self):
        self.assertEqual(
            format_price_with_currency(None, None, "unknown"),
            "قیمت ناموجود",
        )

    def test_hidden_data_warnings_are_not_presented_in_cards(self):
        offer = FlightOffer(offer_id="missing", source="test")
        presented = present_ranked_flight(
            RankedFlight(
                offer,
                None,
                None,
                warnings=(
                    "price is missing or its currency is not confirmed",
                    "valid departure and arrival times are unavailable",
                ),
            )
        )
        self.assertEqual(presented["warnings"], ())

    def test_rank_one_is_marked_as_group_leader(self):
        offer = FlightOffer(offer_id="a", source="test")
        presented = present_ranked_flight(RankedFlight(offer, 1, Decimal("1")))
        self.assertTrue(presented["is_group_leader"])
        self.assertNotIn("score_display", presented)

    def test_known_reasons_and_warnings_are_translated(self):
        self.assertEqual(translate_reason("lower confirmed-currency price"), "قیمت کمتر در همان گروه ارزی")
        self.assertEqual(translate_warning("price is missing or its currency is not confirmed"), "قیمت وجود ندارد یا ارز آن تأیید نشده است.")

    def test_datetime_uses_readable_gregorian_format(self):
        value = datetime(2026, 10, 20, 5, 50)

        self.assertEqual(format_datetime(value), "2026/10/20، 05:50")

