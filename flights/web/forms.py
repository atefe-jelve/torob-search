"""Django form for the source-independent flight search contract."""

from __future__ import annotations

from datetime import date

from django import forms

from flights.domain.contracts import FlightSearch
from flights.services.ranking import RankingPreferences


class FlightSearchForm(forms.Form):
    origin = forms.CharField(label="مبدأ", max_length=20, initial="THR")
    destination = forms.CharField(label="مقصد", max_length=20, initial="MHD")
    departure_date = forms.DateField(
        label="تاریخ رفت",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=date(2026, 10, 25),
    )
    trip_type = forms.ChoiceField(
        label="نوع سفر",
        choices=(("one_way", "یک‌طرفه"), ("round_trip", "رفت‌وبرگشت")),
        initial="one_way",
    )
    return_date = forms.DateField(
        label="تاریخ برگشت",
        help_text="فقط برای سفر رفت‌وبرگشت الزامی است.",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    allow_date_fallback = forms.BooleanField(
        label="اگر در این تاریخ پروازی نبود، تا ۷ روز آینده را هم بررسی کن",
        required=False,
        initial=False,
    )
    passengers = forms.IntegerField(label="تعداد مسافر", min_value=1, initial=1)
    mode = forms.ChoiceField(
        label="مرتب‌سازی بر اساس",
        choices=(
            ("price", "ارزان‌ترین"),
            ("duration", "کوتاه‌ترین مدت سفر"),
            ("departure", "نزدیک‌ترین زمان حرکت"),
        ),
        initial="price",
    )

    flight_type = forms.ChoiceField(
        label="نوع پرواز",
        choices=(
            ("", "همه انواع"),
            ("سیستمی", "سیستمی"),
            ("چارتر", "چارتر"),
        ),
        required=False,
        initial="",
    )

    def clean(self) -> dict:
        cleaned = super().clean()
        if self.errors:
            return cleaned

        try:
            search = FlightSearch(
                origin=cleaned["origin"],
                destination=cleaned["destination"],
                departure_date=cleaned["departure_date"],
                trip_type=cleaned["trip_type"],
                return_date=cleaned.get("return_date"),
                passengers=cleaned["passengers"],
            )
            preferences = RankingPreferences(mode=cleaned["mode"])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

        cleaned["search"] = search
        cleaned["preferences"] = preferences
        return cleaned
