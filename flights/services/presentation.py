"""Presentation-only helpers for ranked flight results."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from flights.domain.normalization import NormalizationIssue
from flights.services.ranking import RankedFlight


REASON_LABELS = {
    "lower confirmed-currency price": "قیمت کمتر در همان گروه ارزی",
    "shorter valid duration": "مدت سفر کوتاه‌تر",
    "price and duration weighted together": "قیمت و مدت سفر هر دو در رتبه‌بندی اثر دارند",
    "price criterion used": "رتبه‌بندی بر اساس قیمت معتبر انجام شده است",
    "duration criterion used": "رتبه‌بندی بر اساس مدت سفر معتبر انجام شده است",
}

WARNING_LABELS = {
    "origin does not match the search": "مبدأ با جست‌وجوی شما مطابقت ندارد.",
    "destination does not match the search": "مقصد با جست‌وجوی شما مطابقت ندارد.",
    "departure date does not match the search": "تاریخ حرکت با جست‌وجوی شما مطابقت ندارد.",
    "origin is missing; search match is unverified": "مبدأ ثبت نشده است؛ تطبیق با جست‌وجو قابل تأیید نیست.",
    "destination is missing; search match is unverified": "مقصد ثبت نشده است؛ تطبیق با جست‌وجو قابل تأیید نیست.",
    "departure date is missing; search match is unverified": "تاریخ حرکت ثبت نشده است؛ تطبیق با جست‌وجو قابل تأیید نیست.",
    "round-trip return-leg data is unavailable in the current contract": "اطلاعات پرواز برگشت در داده فعلی موجود نیست.",
    "price is missing or its currency is not confirmed": "قیمت وجود ندارد یا ارز آن تأیید نشده است.",
    "valid departure and arrival times are unavailable": "زمان معتبر حرکت و رسیدن موجود نیست.",
    "departure time is not in the future": "زمان حرکت این پرواز گذشته است.",
    "excluded from ranking because it does not match the search": "این رکورد با جست‌وجو مطابقت ندارد و در رتبه‌بندی شرکت نکرده است.",
    "record must be a mapping": "ساختار رکورد داده معتبر نیست.",
}

HIDDEN_RESULT_WARNINGS = {
    "price is missing or its currency is not confirmed",
    "valid departure and arrival times are unavailable",
    "departure time is not in the future",
}


def translate_reason(reason: str) -> str:
    return REASON_LABELS.get(reason, "دلیل رتبه‌بندی در دسترس نیست.")


def translate_warning(warning: str) -> str:
    return WARNING_LABELS.get(warning, "هشدار: اطلاعات این پیشنهاد کامل نیست.")


def present_normalization_issue(issue: NormalizationIssue) -> dict:
    return {"index": issue.index, "message": translate_warning(issue.message)}


def duration_minutes(departure_at: Optional[datetime], arrival_at: Optional[datetime]) -> Optional[Decimal]:
    """Return a duration without assigning or converting timezones implicitly."""
    if departure_at is None or arrival_at is None:
        return None
    try:
        seconds = (arrival_at - departure_at).total_seconds()
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return Decimal(str(seconds)) / Decimal("60")


def format_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%Y/%m/%d، %H:%M")


def safe_source_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def format_price(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value, ",f")


_CURRENCY_LABELS = {
    "IRT": "تومان",
    "IRR": "ریال ایران",
    "USD": "دلار آمریکا",
    "EUR": "یورو",
    "AED": "درهم امارات",
}


def currency_label(currency: Optional[str], currency_status: str) -> str:
    if currency_status != "confirmed" or not currency:
        return "واحد پول نامشخص"
    return _CURRENCY_LABELS.get(currency, currency)


def format_price_with_currency(
    value: Optional[Decimal], currency: Optional[str], currency_status: str
) -> str:
    amount = format_price(value)
    if amount is None:
        return "قیمت ناموجود"
    label = currency_label(currency, currency_status)
    return f"{amount} {label}"


def present_ranked_flight(ranked: RankedFlight) -> dict:
    """Convert one ranked result into data suitable for a Django template."""
    offer = ranked.offer
    duration = duration_minutes(offer.departure_at, offer.arrival_at)
    is_excluded = any(
        warning == "excluded from ranking because it does not match the search"
        for warning in ranked.warnings
    )
    return {
        "offer": offer,
        "rank": ranked.rank,
        "is_group_leader": ranked.rank == 1,
        "is_excluded": is_excluded,
        "score": ranked.score,
        "duration_minutes": duration,
        "duration_display": f"{duration:.0f} دقیقه" if duration is not None else None,
        "departure_display": format_datetime(offer.departure_at),
        "arrival_display": format_datetime(offer.arrival_at),
        "price_display": format_price(offer.price_amount),
        "price_with_currency": format_price_with_currency(
            offer.price_amount, offer.currency, offer.currency_status
        ),
        "source_url": safe_source_url(offer.source_url),
        "reasons": tuple(translate_reason(reason) for reason in ranked.reasons),
        "warnings": tuple(
            translate_warning(warning)
            for warning in ranked.warnings
            if warning not in HIDDEN_RESULT_WARNINGS
        ),
        "completeness": ranked.completeness,
    }
