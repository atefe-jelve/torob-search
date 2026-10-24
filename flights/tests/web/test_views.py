import os
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.test import SimpleTestCase
from flights.domain.normalization import NormalizationIssue


POST_DATA = {
    "origin": "THR",
    "destination": "MHD",
    "departure_date": "2026-10-25",
    "trip_type": "one_way",
    "return_date": "",
    "passengers": "1",
    "mode": "price",
}


class SearchViewTests(SimpleTestCase):
    def setUp(self):
        self.reference_now_patch = patch(
            "flights.web.views._reference_now",
            return_value=datetime(2026, 10, 25, 0, 0),
        )
        self.reference_now_patch.start()
        self.addCleanup(self.reference_now_patch.stop)

    def test_homepage_is_available(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "جست‌وجوی پرواز داخلی")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertNotContains(response, "وزن قیمت")
        self.assertNotContains(response, "وزن مدت سفر")
        self.assertNotContains(response, "قیمت و مدت سفر هر دو در رتبه‌بندی اثر دارند")

    def test_valid_post_shows_validation_success_message(self):
        response = self.client.post("/", POST_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ورودی جست‌وجو معتبر است")
        self.assertContains(response, "نتایج آزمایشی")
        self.assertContains(response, "آزمایشی ایر")
        self.assertNotContains(response, "رتبه مستقل در گروه ارز")
        self.assertNotContains(response, "برترین گزینه این گروه")
        self.assertNotContains(response, "رتبه 1")
        self.assertNotContains(response, "رتبه 2")
        self.assertContains(response, "یک برنده جهانی بین ارزها اعلام نمی‌شود")
        self.assertContains(response, "5,599,000")
        self.assertContains(response, "5,599,000 تومان")
        self.assertContains(response, "6,500,000 ریال ایران")
        self.assertContains(response, "مبدأ: THR")
        self.assertContains(response, "مقصد: MHD")
        self.assertNotContains(response, "امتیاز نسبی")
        self.assertNotContains(response, "lower confirmed-currency price")
        self.assertNotContains(response, "برخی رکوردها قابل نرمال‌سازی نبودند")

    def test_primary_date_results_do_not_include_later_dates(self):
        response = self.client.post("/", POST_DATA)

        self.assertContains(response, "آزمایشی ایر")
        self.assertNotContains(response, "نمونه جایگزین یک")

    def test_empty_primary_date_does_not_fallback_when_disabled(self):
        response = self.client.post(
            "/", dict(POST_DATA, departure_date="2026-10-26")
        )

        self.assertContains(response, "برای مسیر و تاریخ انتخاب‌شده، پروازی در داده‌های موجود پیدا نشد")
        self.assertNotContains(response, "نمونه جایگزین یک")

    def test_empty_primary_date_falls_back_up_to_seven_days_when_enabled(self):
        response = self.client.post(
            "/",
            dict(
                POST_DATA,
                departure_date="2026-10-26",
                allow_date_fallback="on",
            ),
        )

        self.assertContains(response, "نمونه جایگزین یک")
        self.assertContains(response, "2026/10/27")
        self.assertNotContains(response, "نمونه فاصله‌دار")

    def test_date_outside_fallback_window_is_not_used(self):
        response = self.client.post(
            "/",
            dict(
                POST_DATA,
                departure_date="2026-11-03",
                allow_date_fallback="on",
            ),
        )

        self.assertContains(response, "برای مسیر و تاریخ انتخاب‌شده، پروازی در داده‌های موجود پیدا نشد")
        self.assertNotContains(response, "نمونه خارج از بازه")

    def test_route_and_type_filters_apply_to_fallback_results(self):
        response = self.client.post(
            "/",
            dict(
                POST_DATA,
                departure_date="2026-10-26",
                flight_type="چارتر",
                allow_date_fallback="on",
            ),
        )

        self.assertContains(response, "نمونه جایگزین دو")
        self.assertNotContains(response, "نمونه جایگزین یک")

    def test_past_flights_are_not_rendered_and_empty_state_is_used(self):
        with patch(
            "flights.web.views._reference_now",
            return_value=datetime(2026, 10, 26, 0, 0),
        ):
            response = self.client.post("/", POST_DATA)
        self.assertContains(response, "برای مسیر و تاریخ انتخاب‌شده، پروازی در داده‌های موجود پیدا نشد")
        self.assertNotContains(response, "زمان حرکت این پرواز گذشته است")

    def test_each_ranking_mode_reaches_ranking_engine(self):
        for mode in ("price", "duration", "departure"):
            with self.subTest(mode=mode), patch("flights.web.views.rank_offers", return_value=[] ) as rank_mock:
                data = dict(POST_DATA, mode=mode)
                response = self.client.post("/", data)

                self.assertEqual(response.status_code, 200)
                preferences = rank_mock.call_args.args[2]
                self.assertEqual(preferences.mode, mode)

    def test_invalid_post_renders_form_errors(self):
        response = self.client.post("/", dict(POST_DATA, origin=""))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "این فیلد لازم است")
        self.assertNotContains(response, "ورودی جست‌وجو معتبر است")

    def test_normalization_issue_is_displayed_without_hiding_valid_results(self):
        with patch(
            "flights.web.views.load_flight_offers",
            return_value=([], [NormalizationIssue(index=3, message="record must be a mapping")]),
        ):
            response = self.client.post("/", POST_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "برخی رکوردها قابل نرمال‌سازی نبودند")
        self.assertContains(response, "رکورد 4")
        self.assertContains(response, "ساختار رکورد داده معتبر نیست")
        self.assertNotContains(response, "record must be a mapping")

    def test_round_trip_results_are_marked_incomplete(self):
        response = self.client.post(
            "/", dict(POST_DATA, trip_type="round_trip", return_date="2026-10-27")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پیشنهاد کامل رفت‌وبرگشت محسوب نمی‌شود")

    def test_missing_source_url_is_safe(self):
        response = self.client.post("/", POST_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "مشاهده منبع")

    @patch("flights.web.views.load_flight_offers")
    def test_loader_error_is_shown_as_user_message(self, load_mock):
        from flights.data.loader import DataLoadError

        load_mock.side_effect = DataLoadError("internal fixture path")
        response = self.client.post("/", POST_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "داده آزمایشی قابل بارگذاری نیست")
        self.assertNotContains(response, "internal fixture path")

    def test_mismatched_offers_are_not_presented_as_valid_results(self):
        response = self.client.post("/", dict(POST_DATA, origin="IFN"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "برای مسیر و تاریخ انتخاب‌شده، پروازی در داده‌های موجود پیدا نشد")
        self.assertNotContains(response, "رکوردهای نامنطبق برای عیب‌یابی")
        self.assertNotContains(response, "پیشنهاد معتبر این جست‌وجو نیستند")

    def test_no_matching_date_uses_product_empty_state_without_debug_details(self):
        response = self.client.post("/", dict(POST_DATA, departure_date="2026-10-21"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "برای مسیر و تاریخ انتخاب‌شده، پروازی در داده‌های موجود پیدا نشد")
        self.assertNotContains(response, "رکوردهای نامنطبق برای عیب‌یابی")

    def test_filter_that_removes_all_offers_uses_product_empty_state(self):
        response = self.client.post("/", dict(POST_DATA, flight_type="سیستمی"))
        self.assertEqual(response.status_code, 200)
        # The fixture has system offers, so use a mocked empty loader to model
        # a valid filter whose remaining set is empty.
        with patch("flights.web.views.load_flight_offers", return_value=([], [])):
            response = self.client.post("/", POST_DATA)
        self.assertContains(response, "برای مسیر و تاریخ انتخاب‌شده، پروازی در داده‌های موجود پیدا نشد")

    def test_flight_type_filter_limits_results(self):
        response = self.client.post("/", dict(POST_DATA, flight_type="چارتر"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نمونه پرواز")
        self.assertNotContains(response, "آزمایشی ایر")

    def test_all_flight_types_keeps_all_fixture_types(self):
        response = self.client.post("/", dict(POST_DATA, flight_type=""))

        self.assertContains(response, "آزمایشی ایر")
        self.assertContains(response, "نمونه پرواز")

    def test_specific_flight_type_excludes_offer_without_type(self):
        from flights.domain.contracts import FlightOffer
        from decimal import Decimal
        from datetime import datetime

        missing_type = FlightOffer(
            offer_id="missing-type",
            source="test",
            origin="THR",
            destination="MHD",
            departure_at=datetime(2026, 10, 20, 6),
            arrival_at=datetime(2026, 10, 20, 7),
            price_amount=Decimal("100"),
            currency="IRT",
            currency_status="confirmed",
            flight_type=None,
        )
        with patch("flights.web.views.load_flight_offers", return_value=([missing_type], [])):
            response = self.client.post("/", dict(POST_DATA, flight_type="سیستمی"))

        self.assertContains(response, "برای مسیر و تاریخ انتخاب‌شده، پروازی در داده‌های موجود پیدا نشد")
