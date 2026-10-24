"""Normalize local source JSON into :class:`FlightOffer` values.

The source schema is intentionally treated as unstable.  Unknown/missing fields
become ``None``; no route or round-trip relationship is inferred here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Optional

from .contracts import FlightOffer


@dataclass(frozen=True)
class NormalizationIssue:
    """A record-level problem; one issue does not abort a batch."""

    index: Optional[int]
    message: str
    record: Any = None


_MISSING = object()
_ALIASES = {
    "origin": ("origin", "originCode", "from", "departureAirport"),
    "destination": ("destination", "destinationCode", "to", "arrivalAirport"),
    "departure": ("departureDateTime", "departure_datetime", "departureAt", "departure"),
    "arrival": ("arrivalDateTime", "arrival_datetime", "arrivalAt", "arrivalTime", "arrival"),
    "airline": ("airline", "airlineName", "carrier"),
    "flight_type": ("flightType", "fareType", "ticketType", "type"),
    "aircraft": ("aircraftType", "aircraft", "planeType"),
    "price": ("adultPrice", "price", "amount", "priceAmount"),
    "currency": ("currency", "currencyCode", "currencyName", "unit"),
    # ``systemKey`` was observed in source JSON, but its identity semantics
    # are not established; do not expose it as a stable offer identifier.
    "source_id": ("offerId", "id"),
    "source_url": ("sourceUrl", "bookingUrl", "url", "link"),
}


def _value(record: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("name") or value.get("code") or value.get("title")
    text = str(value).strip()
    return text or None


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _parse_decimal(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).translate(_PERSIAN_DIGITS).strip()
    text = re.sub(r"[^0-9+\-.]", "", text.replace(",", ""))
    if not text or text in {"+", "-", ".", "+.", "-."}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def canonical_currency(value: Any) -> tuple[Optional[str], str]:
    """Return a canonical code without converting amounts between currencies."""
    if value is None:
        return None, "unknown"
    text = str(value).translate(_PERSIAN_DIGITS).strip().lower()
    compact = re.sub(r"[\s_-]+", "", text)
    if compact in {"irr", "rial", "rials", "ریال", "ریالایران"}:
        return "IRR", "confirmed"
    if compact in {"irt", "toman", "tomans", "تومان", "تومن"}:
        return "IRT", "confirmed"
    # ISO codes for other currencies are safe to retain, but unknown labels are not.
    if re.fullmatch(r"[a-z]{3}", compact):
        return compact.upper(), "confirmed"
    return None, "unknown"


def parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
        # A time-only arrival does not identify the arrival date; do not guess it.
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _stable_id(record: Mapping[str, Any], source: str) -> str:
    raw = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(f"{source}:{raw}".encode("utf-8")).hexdigest()[:20]
    return f"{source}:generated-{digest}"


def normalize_record(
    record: Mapping[str, Any],
    *,
    source: str = "local",
    source_url: Optional[str] = None,
    observed_at: Optional[datetime] = None,
) -> FlightOffer:
    """Normalize one mapping, raising ``ValueError`` for an unusable record."""
    if not isinstance(record, Mapping):
        raise ValueError("record must be a mapping")
    if not source or not source.strip():
        raise ValueError("source must not be empty")
    raw_id = _text(_value(record, _ALIASES["source_id"]))
    offer_id = raw_id if raw_id else _stable_id(record, source)
    currency, currency_status = canonical_currency(_value(record, _ALIASES["currency"]))
    return FlightOffer(
        offer_id=offer_id,
        source=source,
        origin=_text(_value(record, _ALIASES["origin"])),
        destination=_text(_value(record, _ALIASES["destination"])),
        departure_at=parse_datetime(_value(record, _ALIASES["departure"])),
        arrival_at=parse_datetime(_value(record, _ALIASES["arrival"])),
        airline=_text(_value(record, _ALIASES["airline"])),
        flight_type=_text(_value(record, _ALIASES["flight_type"])),
        aircraft_type=_text(_value(record, _ALIASES["aircraft"])),
        price_amount=_parse_decimal(_value(record, _ALIASES["price"])),
        currency=currency,
        currency_status=currency_status,
        source_url=_text(source_url or _value(record, _ALIASES["source_url"])),
        observed_at=observed_at or datetime.now(timezone.utc),
    )


def normalize_records(
    records: Iterable[Mapping[str, Any]],
    *,
    source: str = "local",
    source_url: Optional[str] = None,
    observed_at: Optional[datetime] = None,
) -> tuple[list[FlightOffer], list[NormalizationIssue]]:
    """Normalize a batch while returning record-level errors separately."""
    offers: list[FlightOffer] = []
    issues: list[NormalizationIssue] = []
    for index, record in enumerate(records):
        try:
            offers.append(normalize_record(record, source=source, source_url=source_url, observed_at=observed_at))
        except (TypeError, ValueError, InvalidOperation) as exc:
            issues.append(NormalizationIssue(index=index, message=str(exc), record=record))
    return offers, issues

