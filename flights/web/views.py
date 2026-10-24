"""Django view connecting the local fixture to the ranking engine."""

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from django.shortcuts import render

from flights.data.loader import DataLoadError, load_flight_offers
from flights.services.presentation import present_normalization_issue, present_ranked_flight
from flights.services.ranking import departure_temporal_status, rank_offers

from .forms import FlightSearchForm

logger = logging.getLogger(__name__)
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_flights.json"


def _reference_now() -> datetime:
    return datetime.now()


def _rank_for_date(offers, search, preferences, target_date: date, reference_now):
    """Rank only offers whose known departure date is the selected date."""
    dated_offers = [
        offer
        for offer in offers
        if (
            offer.departure_at is None
            and target_date == search.departure_date
        )
        or (
            offer.departure_at is not None
            and offer.departure_at.date() == target_date
        )
    ]
    if not dated_offers:
        return []
    date_search = replace(search, departure_date=target_date)
    ranked = rank_offers(
        dated_offers,
        date_search,
        preferences,
        reference_now=reference_now,
    )
    return [
        item
        for item in ranked
        if not any(
            warning == "excluded from ranking because it does not match the search"
            for warning in item.warnings
        )
        and departure_temporal_status(item.offer.departure_at, reference_now) != "past"
    ]


def search_view(request):
    form = FlightSearchForm(request.POST or None)
    submitted = request.method == "POST"
    valid_submission = False
    results = []
    excluded_results = []
    normalization_issues = []
    load_error = None
    if request.method == "POST" and form.is_valid():
        valid_submission = True
        search = form.cleaned_data["search"]
        preferences = form.cleaned_data["preferences"]
        try:
            offers, issues = load_flight_offers(FIXTURE_PATH)
            normalization_issues = [present_normalization_issue(issue) for issue in issues]
            selected_flight_type = form.cleaned_data.get("flight_type")
            if selected_flight_type:
                offers = [
                    offer for offer in offers if offer.flight_type == selected_flight_type
                ]
            reference_now = _reference_now()
            fallback_enabled = form.cleaned_data.get("allow_date_fallback", False)
            dates_to_check = [search.departure_date]
            if fallback_enabled:
                dates_to_check.extend(
                    search.departure_date + timedelta(days=offset)
                    for offset in range(1, 8)
                )
            for target_date in dates_to_check:
                ranked = _rank_for_date(
                    offers, search, preferences, target_date, reference_now
                )
                if ranked:
                    results = [present_ranked_flight(item) for item in ranked]
                    break
        except DataLoadError:
            load_error = "داده آزمایشی قابل بارگذاری نیست. لطفاً وضعیت فایل داده را بررسی کنید."
        except Exception:
            logger.exception("Unexpected error while processing local flight fixture")
            load_error = "خطای غیرمنتظره‌ای هنگام پردازش جست‌وجو رخ داد."

    return render(
        request,
        "flights/search.html",
        {
            "form": form,
            "submitted": submitted,
            "valid_submission": valid_submission,
            "results": results,
            "normalization_issues": normalization_issues,
            "load_error": load_error,
        },
    )
