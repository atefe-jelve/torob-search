import unittest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from flights.domain.contracts import FlightOffer, FlightSearch
from flights.services.ranking import RankingPreferences, departure_temporal_status, rank_offers


SEARCH = FlightSearch("THR", "MHD", date(2026, 10, 20))


def offer(
    offer_id: str,
    *,
    price: str | None = "100",
    currency: str | None = "IRT",
    departure_hour: int | None = 5,
    arrival_hour: int | None = 7,
    origin: str | None = "THR",
    destination: str | None = "MHD",
) -> FlightOffer:
    return FlightOffer(
        offer_id=offer_id,
        source="test",
        origin=origin,
        destination=destination,
        departure_at=datetime(2026, 10, 20, departure_hour, 0) if departure_hour is not None else None,
        arrival_at=datetime(2026, 10, 20, arrival_hour, 0) if arrival_hour is not None else None,
        price_amount=Decimal(price) if price is not None else None,
        currency=currency,
        currency_status="confirmed" if currency is not None else "unknown",
    )


class RankingTests(unittest.TestCase):
    def test_price_mode_ranks_lower_price_first(self):
        result = rank_offers([offer("expensive", price="200"), offer("cheap", price="100")], SEARCH)

        self.assertEqual([item.offer.offer_id for item in result], ["cheap", "expensive"])
        self.assertEqual([item.rank for item in result], [1, 2])
        self.assertGreater(result[0].score, result[1].score)

    def test_duration_mode_ranks_shorter_duration_first(self):
        result = rank_offers(
            [offer("long", price="100", departure_hour=5, arrival_hour=9), offer("short", price="200", departure_hour=5, arrival_hour=6)],
            SEARCH,
            RankingPreferences(mode="duration"),
        )

        self.assertEqual([item.offer.offer_id for item in result], ["short", "long"])

    def test_departure_mode_ranks_nearest_future_departures_first(self):
        result = rank_offers(
            [
                offer("future-near", departure_hour=7),
                offer("future-far", departure_hour=8),
                offer("past", departure_hour=5),
            ],
            SEARCH,
            RankingPreferences(mode="departure"),
            reference_now=datetime(2026, 10, 20, 6, 0),
        )

        self.assertEqual([item.offer.offer_id for item in result], ["future-near", "future-far", "past"])
        self.assertEqual([item.rank for item in result], [1, 2, None])
        self.assertIn("departure time is not in the future", result[-1].warnings)

    def test_departure_mode_uses_full_time_and_places_invalid_last(self):
        result = rank_offers(
            [
                offer("past-late", departure_hour=5, arrival_hour=7),
                offer("future-late", departure_hour=9, arrival_hour=10),
                offer("future-early", departure_hour=7, arrival_hour=8),
                offer("missing-time", departure_hour=None, arrival_hour=None),
            ],
            SEARCH,
            RankingPreferences(mode="departure"),
            reference_now=datetime(2026, 10, 20, 6, 30),
        )

        self.assertEqual(
            [item.offer.offer_id for item in result],
            ["future-early", "future-late", "past-late", "missing-time"],
        )
        self.assertEqual([item.rank for item in result], [1, 2, None, None])

    def test_departure_mode_orders_past_records_by_complete_timestamp(self):
        result = rank_offers(
            [offer("later-past", departure_hour=15), offer("earlier-past", departure_hour=5)],
            SEARCH,
            RankingPreferences(mode="departure"),
            reference_now=datetime(2026, 10, 20, 18, 0),
        )
        self.assertEqual([item.offer.offer_id for item in result], ["earlier-past", "later-past"])

    def test_departure_temporal_status_keeps_missing_time_unknown(self):
        reference = datetime(2026, 10, 20, 6, 0)
        self.assertEqual(departure_temporal_status(offer("future").departure_at, reference), "past")
        self.assertEqual(departure_temporal_status(None, reference), "unknown")

    def test_balanced_mode_uses_configurable_weights(self):
        result = rank_offers(
            [offer("cheap-long", price="100", departure_hour=5, arrival_hour=9), offer("expensive-short", price="200", departure_hour=5, arrival_hour=6)],
            SEARCH,
            RankingPreferences(mode="balanced", price_weight=Decimal("0.8"), duration_weight=Decimal("0.2")),
        )

        self.assertEqual(result[0].offer.offer_id, "cheap-long")

    def test_balanced_reasons_reflect_only_metrics_used(self):
        missing_price = offer("missing-price", price=None, currency="IRT", departure_hour=5, arrival_hour=6)
        missing_duration = offer("missing-duration", price="100", departure_hour=None, arrival_hour=6)

        price_result = rank_offers(
            [missing_price], SEARCH,
            RankingPreferences(mode="balanced"),
        )[0]
        duration_result = rank_offers(
            [missing_duration], SEARCH,
            RankingPreferences(mode="balanced"),
        )[0]

        self.assertEqual(price_result.reasons, ("duration criterion used",))
        self.assertEqual(duration_result.reasons, ("price criterion used",))

    def test_zero_weight_excludes_that_metric_from_balanced_score(self):
        result = rank_offers(
            [offer("short", price="200", departure_hour=5, arrival_hour=6), offer("long", price="100", departure_hour=5, arrival_hour=9)],
            SEARCH,
            RankingPreferences(mode="balanced", price_weight=Decimal("0"), duration_weight=Decimal("1")),
        )

        self.assertEqual(result[0].offer.offer_id, "short")
        self.assertEqual(result[0].reasons, ("duration criterion used",))

    def test_negative_and_zero_total_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            RankingPreferences(mode="balanced", price_weight=Decimal("-1"), duration_weight=Decimal("1"))
        with self.assertRaises(ValueError):
            RankingPreferences(mode="balanced", price_weight=Decimal("0"), duration_weight=Decimal("0"))

    def test_currencies_are_ranked_in_separate_groups(self):
        result = rank_offers(
            [offer("toman", price="1", currency="IRT"), offer("rial", price="1", currency="IRR")],
            SEARCH,
        )

        self.assertEqual({item.offer.currency for item in result}, {"IRT", "IRR"})
        self.assertEqual([item.rank for item in result], [1, 1])

    def test_balanced_currencies_are_separate(self):
        offers = [
            offer("toman", price="1", currency="IRT", departure_hour=5, arrival_hour=6),
            offer("rial", price="1", currency="IRR", departure_hour=5, arrival_hour=8),
        ]
        result = rank_offers(offers, SEARCH, RankingPreferences(mode="balanced"))
        self.assertEqual([item.rank for item in result], [1, 1])

    def test_duration_mode_orders_valid_durations_across_currency_groups(self):
        offers = [
            offer("long-foreign", price="1", currency="IRR", departure_hour=5, arrival_hour=8),
            offer("short-toman", price="999999999", currency="IRT", departure_hour=5, arrival_hour=6),
        ]

        result = rank_offers(offers, SEARCH, RankingPreferences(mode="duration"))

        self.assertEqual([item.offer.offer_id for item in result], ["short-toman", "long-foreign"])
        self.assertEqual([item.rank for item in result], [1, 2])

    def test_missing_price_is_kept_but_not_ranked_in_price_mode(self):
        result = rank_offers([offer("missing", price=None, currency=None), offer("priced", price="100")], SEARCH)

        missing = next(item for item in result if item.offer.offer_id == "missing")
        self.assertIsNone(missing.rank)
        self.assertIsNone(missing.score)
        self.assertTrue(any("price" in warning for warning in missing.warnings))

    def test_missing_duration_is_kept_but_not_ranked_in_duration_mode(self):
        result = rank_offers(
            [offer("missing", departure_hour=None), offer("timed", departure_hour=5, arrival_hour=6)],
            SEARCH,
            RankingPreferences(mode="duration"),
        )

        missing = next(item for item in result if item.offer.offer_id == "missing")
        self.assertIsNone(missing.rank)
        self.assertTrue(any("times" in warning for warning in missing.warnings))

    def test_equal_scores_use_departure_then_offer_id_as_tie_breakers(self):
        result = rank_offers(
            [offer("b", price="100", departure_hour=6), offer("a", price="100", departure_hour=5)],
            SEARCH,
        )

        self.assertEqual([item.offer.offer_id for item in result], ["a", "b"])

    def test_singleton_and_equal_criteria_have_deterministic_scores(self):
        singleton = rank_offers([offer("only")], SEARCH)[0]
        self.assertEqual(singleton.rank, 1)
        self.assertEqual(singleton.score, Decimal("1"))

        result = rank_offers(
            [offer("b", price="100", departure_hour=5), offer("a", price="100", departure_hour=5)],
            SEARCH,
        )
        self.assertEqual([item.offer.offer_id for item in result], ["a", "b"])
        self.assertEqual([item.score for item in result], [Decimal("1"), Decimal("1")])

    def test_timezone_aware_duration_crossing_midnight_is_supported(self):
        departure = datetime(2026, 10, 20, 23, 30, tzinfo=timezone(timedelta(hours=3, minutes=30)))
        arrival = datetime(2026, 10, 21, 0, 30, tzinfo=timezone(timedelta(hours=3, minutes=30)))
        aware_offer = FlightOffer(
            offer_id="aware",
            source="test",
            origin="THR",
            destination="MHD",
            departure_at=departure,
            arrival_at=arrival,
            price_amount=Decimal("100"),
            currency="IRT",
            currency_status="confirmed",
        )

        result = rank_offers([aware_offer], SEARCH, RankingPreferences(mode="duration"))[0]

        self.assertEqual(result.rank, 1)
        self.assertEqual(result.score, Decimal("1"))

    def test_timezone_aware_departure_sort_uses_absolute_instant(self):
        earlier = FlightOffer(
            offer_id="earlier",
            source="test",
            origin="THR",
            destination="MHD",
            departure_at=datetime(2026, 10, 20, 23, 30, tzinfo=timezone(timedelta(hours=3, minutes=30))),
            arrival_at=datetime(2026, 10, 21, 0, 30, tzinfo=timezone(timedelta(hours=3, minutes=30))),
            price_amount=Decimal("100"),
            currency="IRT",
            currency_status="confirmed",
        )
        later = FlightOffer(
            offer_id="later",
            source="test",
            origin="THR",
            destination="MHD",
            departure_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
            arrival_at=datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc),
            price_amount=Decimal("100"),
            currency="IRT",
            currency_status="confirmed",
        )

        result = rank_offers([earlier, later], SEARCH, RankingPreferences(mode="duration"))

        self.assertEqual([item.offer.offer_id for item in result], ["earlier", "later"])

    def test_mixed_naive_and_aware_datetimes_are_not_guessed(self):
        mixed = FlightOffer(
            offer_id="mixed",
            source="test",
            origin="THR",
            destination="MHD",
            departure_at=datetime(2026, 10, 20, 5, tzinfo=timezone.utc),
            arrival_at=datetime(2026, 10, 20, 7),
            price_amount=Decimal("100"),
            currency="IRT",
            currency_status="confirmed",
        )

        result = rank_offers([mixed], SEARCH, RankingPreferences(mode="duration"))[0]

        self.assertIsNone(result.rank)
        self.assertTrue(any("times" in warning for warning in result.warnings))

    def test_empty_input_returns_empty_result(self):
        self.assertEqual(rank_offers([], SEARCH), [])

    def test_non_matching_known_route_is_unranked_with_warning(self):
        result = rank_offers([offer("wrong", origin="IFN")], SEARCH)

        self.assertIsNone(result[0].rank)
        self.assertTrue(any("does not match" in warning for warning in result[0].warnings))

    def test_round_trip_is_explicitly_limited(self):
        search = FlightSearch("THR", "MHD", date(2026, 10, 20), trip_type="round_trip", return_date=date(2026, 10, 22))
        result = rank_offers([offer("outbound")], search)

        self.assertEqual(result[0].completeness, "incomplete")
        self.assertIsNone(result[0].rank)
        self.assertIsNone(result[0].score)
        self.assertTrue(any("return-leg" in warning for warning in result[0].warnings))

    def test_one_way_remains_rankable_and_complete(self):
        result = rank_offers([offer("outbound")], SEARCH)

        self.assertEqual(result[0].completeness, "complete")
        self.assertEqual(result[0].rank, 1)

    def test_duplicate_offer_ids_do_not_overwrite_each_other(self):
        result = rank_offers(
            [offer("duplicate", price="100"), offer("duplicate", price="200")],
            SEARCH,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual([item.rank for item in result], [1, 2])


if __name__ == "__main__":
    unittest.main()
