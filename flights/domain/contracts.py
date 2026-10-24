"""Source-independent data contracts for the first flight-search iteration."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional


TripType = Literal["one_way", "round_trip"]
CurrencyStatus = Literal["confirmed", "unknown"]


@dataclass(frozen=True)
class FlightSearch:
    """The small, source-independent input to a local JSON search."""

    origin: str
    destination: str
    departure_date: date
    trip_type: TripType = "one_way"
    return_date: Optional[date] = None
    passengers: int = 1

    def __post_init__(self) -> None:
        if not self.origin or not self.origin.strip():
            raise ValueError("origin must not be empty")
        if not self.destination or not self.destination.strip():
            raise ValueError("destination must not be empty")
        if self.trip_type not in ("one_way", "round_trip"):
            raise ValueError("trip_type must be 'one_way' or 'round_trip'")
        if self.passengers < 1:
            raise ValueError("passengers must be at least 1")
        if self.trip_type == "round_trip" and self.return_date is None:
            raise ValueError("return_date is required for round_trip searches")
        if self.return_date is not None and self.return_date < self.departure_date:
            raise ValueError("return_date cannot precede departure_date")


@dataclass(frozen=True)
class FlightOffer:
    """A normalized offer; it intentionally has no Django/ORM dependency."""

    offer_id: str
    source: str
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_at: Optional[datetime] = None
    arrival_at: Optional[datetime] = None
    airline: Optional[str] = None
    flight_type: Optional[str] = None
    aircraft_type: Optional[str] = None
    price_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    currency_status: CurrencyStatus = "unknown"
    source_url: Optional[str] = None
    observed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.offer_id or not self.offer_id.strip():
            raise ValueError("offer_id must not be empty")
        if not self.source or not self.source.strip():
            raise ValueError("source must not be empty")
        if self.price_amount is not None and self.price_amount < 0:
            raise ValueError("price_amount cannot be negative")
        if self.currency_status not in ("confirmed", "unknown"):
            raise ValueError("currency_status must be 'confirmed' or 'unknown'")
        if self.currency_status == "unknown" and self.currency is not None:
            raise ValueError("unknown currency status cannot have a currency code")
        if self.currency_status == "confirmed" and not self.currency:
            raise ValueError("confirmed currency status requires a currency code")

