"""Deterministic ranking for normalized flight offers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional, Sequence

from flights.domain.contracts import FlightOffer, FlightSearch


RankingMode = Literal["price", "duration", "balanced", "departure"]
Completeness = Literal["complete", "incomplete"]


@dataclass(frozen=True)
class RankingPreferences:
    """User-adjustable ranking mode and weights."""

    mode: RankingMode = "price"
    price_weight: Decimal = Decimal("0.5")
    duration_weight: Decimal = Decimal("0.5")

    def __post_init__(self) -> None:
        if self.mode not in ("price", "duration", "balanced", "departure"):
            raise ValueError("mode must be 'price', 'duration', 'balanced' or 'departure'")
        if self.price_weight < 0 or self.duration_weight < 0:
            raise ValueError("weights cannot be negative")
        if self.mode == "balanced" and self.price_weight + self.duration_weight <= 0:
            raise ValueError("balanced ranking requires a positive total weight")


@dataclass(frozen=True)
class RankedFlight:
    """A ranked offer plus machine-readable reasons and limitations."""

    offer: FlightOffer
    rank: Optional[int]
    score: Optional[Decimal]
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    completeness: Completeness = "complete"


def _currency_group(offer: FlightOffer) -> str:
    if offer.currency_status == "confirmed" and offer.currency:
        return offer.currency
    return "unknown"


def _duration_minutes(offer: FlightOffer) -> Optional[Decimal]:
    """Return duration without timezone conversion or timezone assumptions.

    Python handles midnight crossings and aware-to-aware datetime arithmetic.
    A naive/aware mixture is intentionally treated as unavailable rather than
    guessing a timezone.
    """
    if offer.departure_at is None or offer.arrival_at is None:
        return None
    try:
        seconds = (offer.arrival_at - offer.departure_at).total_seconds()
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return Decimal(str(seconds)) / Decimal("60")


def _valid_price(offer: FlightOffer) -> bool:
    return (
        offer.price_amount is not None
        and offer.price_amount >= 0
        and offer.currency_status == "confirmed"
        and bool(offer.currency)
    )


def _date_matches(value: Optional[datetime], expected: date) -> Optional[bool]:
    if value is None:
        return None
    return value.date() == expected


def _search_warnings(offer: FlightOffer, search: FlightSearch) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    matches = True
    if offer.origin is not None and offer.origin.casefold() != search.origin.casefold():
        matches = False
        warnings.append("origin does not match the search")
    elif offer.origin is None:
        warnings.append("origin is missing; search match is unverified")
    if offer.destination is not None and offer.destination.casefold() != search.destination.casefold():
        matches = False
        warnings.append("destination does not match the search")
    elif offer.destination is None:
        warnings.append("destination is missing; search match is unverified")
    departure_match = _date_matches(offer.departure_at, search.departure_date)
    if departure_match is False:
        matches = False
        warnings.append("departure date does not match the search")
    elif departure_match is None:
        warnings.append("departure date is missing; search match is unverified")
    if search.trip_type == "round_trip":
        warnings.append("round-trip return-leg data is unavailable in the current contract")
    return matches, warnings


def _normalized_lower_is_better(values: dict[int, Decimal], key: int) -> Decimal:
    value = values[key]
    minimum = min(values.values())
    maximum = max(values.values())
    if minimum == maximum:
        return Decimal("1")
    return Decimal("1") - ((value - minimum) / (maximum - minimum))


def _departure_sort_key(value: Optional[datetime]) -> tuple[int, str, str]:
    """Sort known datetimes chronologically without mixing timezone policies.

    Aware values are compared after representing the same instant in UTC;
    naive values remain wall-clock values and are never assigned a timezone.
    Naive and aware values are kept in separate deterministic buckets.
    """
    if value is None:
        return (2, "", "")
    if value.tzinfo is not None and value.utcoffset() is not None:
        return (0, "aware", value.astimezone(timezone.utc).isoformat())
    return (1, "naive", value.isoformat())


def _departure_future_sort_key(
    value: Optional[datetime], reference_now: datetime
) -> tuple[int, float, str]:
    """Sort future departures first, without mixing naive and aware datetimes."""
    if value is None:
        return (2, float("inf"), "")
    value_aware = value.tzinfo is not None and value.utcoffset() is not None
    now_aware = reference_now.tzinfo is not None and reference_now.utcoffset() is not None
    if value_aware != now_aware:
        return (2, float("inf"), value.isoformat())
    seconds = (value - reference_now).total_seconds()
    if seconds > 0:
        return (0, seconds, value.isoformat())
    # Past departures remain after all future departures. Within that bucket,
    # keep their complete departure timestamp as the deterministic order rather
    # than sorting by distance from ``reference_now``.
    if value_aware:
        sort_value = value.astimezone(timezone.utc).isoformat()
    else:
        sort_value = value.isoformat()
    return (1, 0.0, sort_value)


def _is_future_departure(value: Optional[datetime], reference_now: datetime) -> bool:
    return _departure_future_sort_key(value, reference_now)[0] == 0


def departure_temporal_status(value: Optional[datetime], reference_now: datetime) -> str:
    """Classify a departure without guessing across incompatible timezones."""
    bucket = _departure_future_sort_key(value, reference_now)[0]
    if bucket == 0:
        return "future"
    if bucket == 1:
        return "past"
    return "unknown"


def _rank_group(
    offers: Sequence[FlightOffer],
    search: FlightSearch,
    preferences: RankingPreferences,
    reference_now: datetime,
) -> list[RankedFlight]:
    trip_incomplete = search.trip_type == "round_trip"
    candidates: list[tuple[FlightOffer, list[str]]] = []
    excluded: list[RankedFlight] = []
    for offer in offers:
        matches, warnings = _search_warnings(offer, search)
        if not matches:
            excluded.append(
                RankedFlight(
                    offer,
                    None,
                    None,
                    (),
                    tuple(warnings + ["excluded from ranking because it does not match the search"]),
                    "incomplete" if trip_incomplete else "complete",
                )
            )
        else:
            candidates.append((offer, warnings))

    # Index by candidate position rather than offer_id so duplicate source IDs
    # cannot overwrite each other.
    prices = {
        index: offer.price_amount
        for index, (offer, _) in enumerate(candidates)
        if _valid_price(offer)
    }
    durations = {
        index: _duration_minutes(offer)
        for index, (offer, _) in enumerate(candidates)
    }
    valid_durations = {key: value for key, value in durations.items() if value is not None}
    valid_prices = {key: value for key, value in prices.items() if value is not None}

    scored: list[tuple[FlightOffer, list[str], list[str], tuple[str, ...], Optional[Decimal]]] = []
    for index, (offer, warnings) in enumerate(candidates):
        offer_warnings = list(warnings)
        used_metrics: list[str] = []
        score: Optional[Decimal] = None
        price_score: Optional[Decimal] = None
        duration_score: Optional[Decimal] = None
        if _valid_price(offer):
            price_score = _normalized_lower_is_better(valid_prices, index)
        else:
            offer_warnings.append("price is missing or its currency is not confirmed")
        duration = durations.get(index)
        if duration is not None:
            duration_score = _normalized_lower_is_better(valid_durations, index)
        else:
            offer_warnings.append("valid departure and arrival times are unavailable")
        if preferences.mode == "departure" and offer.departure_at is not None and not _is_future_departure(offer.departure_at, reference_now):
            offer_warnings.append("departure time is not in the future")

        if preferences.mode == "price":
            score = price_score
            if score is not None:
                used_metrics.append("price")
        elif preferences.mode == "duration":
            score = duration_score
            if score is not None:
                used_metrics.append("duration")
        else:
            weighted: list[tuple[Decimal, Decimal]] = []
            if price_score is not None and preferences.price_weight > 0:
                weighted.append((price_score, preferences.price_weight))
                used_metrics.append("price")
            if duration_score is not None and preferences.duration_weight > 0:
                weighted.append((duration_score, preferences.duration_weight))
                used_metrics.append("duration")
            total_weight = sum((weight for _, weight in weighted), Decimal("0"))
            if total_weight > 0:
                score = sum((value * weight for value, weight in weighted), Decimal("0")) / total_weight
        scored.append((offer, warnings, offer_warnings, tuple(used_metrics), score))

    if trip_incomplete:
        scored.sort(key=lambda item: (_departure_sort_key(item[0].departure_at), item[0].offer_id))
    elif preferences.mode == "departure":
        scored.sort(key=lambda item: (_departure_future_sort_key(item[0].departure_at, reference_now), item[0].offer_id))
    else:
        scored.sort(
            key=lambda item: (
                item[4] is None,
                -(item[4] or Decimal("0")),
                _departure_sort_key(item[0].departure_at),
                item[0].offer_id,
            )
        )
    ranked: list[RankedFlight] = []
    next_rank = 1
    for offer, _, warnings, used_metrics, score in scored:
        rank = None
        exposed_score = None if trip_incomplete else score
        if preferences.mode == "departure":
            if _is_future_departure(offer.departure_at, reference_now):
                rank = next_rank
                next_rank += 1
        elif exposed_score is not None:
            rank = next_rank
            next_rank += 1
        ranked.append(
            RankedFlight(
                offer,
                rank,
                exposed_score,
                tuple(_reasons_for(preferences, exposed_score, used_metrics)),
                tuple(warnings),
                "incomplete" if trip_incomplete else "complete",
            )
        )
    return ranked + sorted(excluded, key=lambda item: item.offer.offer_id)


def _reasons_for(
    preferences: RankingPreferences,
    score: Optional[Decimal],
    used_metrics: tuple[str, ...],
) -> list[str]:
    if score is None:
        return []
    if preferences.mode == "price":
        return ["lower confirmed-currency price"]
    if preferences.mode == "duration":
        return ["shorter valid duration"]
    if used_metrics == ("price", "duration") or used_metrics == ("duration", "price"):
        return ["price and duration weighted together"]
    if used_metrics == ("price",):
        return ["price criterion used"]
    if used_metrics == ("duration",):
        return ["duration criterion used"]
    return []


def rank_offers(
    offers: Sequence[FlightOffer],
    search: FlightSearch,
    preferences: Optional[RankingPreferences] = None,
    *,
    reference_now: Optional[datetime] = None,
) -> list[RankedFlight]:
    """Rank offers with currency groups for price-based modes only."""
    if not offers:
        return []
    preferences = preferences or RankingPreferences()
    reference_now = reference_now or datetime.now()
    # Prices and weighted scores are only comparable inside one confirmed
    # currency group. Duration and departure time are currency-independent,
    # so those modes must use one group to keep their primary criterion global.
    if preferences.mode in ("duration", "departure"):
        groups = {"all": list(offers)}
    else:
        groups: dict[str, list[FlightOffer]] = {}
        for offer in offers:
            groups.setdefault(_currency_group(offer), []).append(offer)
    ranked: list[RankedFlight] = []
    for group in sorted(groups):
        ranked.extend(_rank_group(groups[group], search, preferences, reference_now))
    return ranked
