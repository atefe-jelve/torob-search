import os
import unittest
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from flights.web.forms import FlightSearchForm


def valid_data(**overrides):
    data = {
        "origin": "THR",
        "destination": "MHD",
        "departure_date": "2026-10-25",
        "trip_type": "one_way",
        "return_date": "",
        "passengers": "1",
        "mode": "price",
    }
    data.update(overrides)
    return data


class FlightSearchFormTests(unittest.TestCase):
    def test_ranking_choices_are_simple_persian_labels(self):
        labels = dict(FlightSearchForm.base_fields["mode"].choices)

        self.assertIn("ارزان‌ترین", labels["price"])
        self.assertIn("کوتاه‌ترین مدت سفر", labels["duration"])
        self.assertIn("نزدیک‌ترین زمان حرکت", labels["departure"])
        self.assertNotIn("balanced", labels)

    def test_flight_type_filter_choices_match_fixture_values(self):
        choices = dict(FlightSearchForm.base_fields["flight_type"].choices)

        self.assertEqual(choices[""], "همه انواع")
        self.assertIn("سیستمی", choices)
        self.assertIn("چارتر", choices)

    def test_demo_initial_values_match_project_fixture(self):
        form = FlightSearchForm()

        self.assertEqual(form.fields["origin"].initial, "THR")
        self.assertEqual(form.fields["destination"].initial, "MHD")
        self.assertEqual(form.fields["departure_date"].initial, date(2026, 10, 25))
        self.assertFalse(form.fields["allow_date_fallback"].initial)

    def test_valid_form_builds_domain_objects(self):
        form = FlightSearchForm(valid_data())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["search"].origin, "THR")
        self.assertEqual(form.cleaned_data["search"].departure_date, date(2026, 10, 25))
        self.assertEqual(form.cleaned_data["preferences"].price_weight, form.cleaned_data["preferences"].duration_weight)

    def test_blank_origin_or_destination_is_rejected(self):
        for field in ("origin", "destination"):
            with self.subTest(field=field):
                form = FlightSearchForm(valid_data(**{field: ""}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_round_trip_requires_return_date(self):
        form = FlightSearchForm(valid_data(trip_type="round_trip", return_date=""))

        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_return_date_before_departure_is_rejected(self):
        form = FlightSearchForm(
            valid_data(trip_type="round_trip", return_date="2026-10-19")
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_invalid_passenger_count_is_rejected(self):
        form = FlightSearchForm(valid_data(passengers="0"))

        self.assertFalse(form.is_valid())
        self.assertIn("passengers", form.errors)


