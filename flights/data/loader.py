"""Load local JSON fixtures and pass records to the existing normalizer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from flights.domain.contracts import FlightOffer
from flights.domain.normalization import NormalizationIssue, normalize_records


class DataLoadError(ValueError):
    """Raised when a local fixture cannot be read or has an invalid envelope."""


def _records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("offers"), list):
        return payload["offers"]
    raise DataLoadError("fixture JSON must be a list or an object with an 'offers' list")


def load_json_records(path: str | Path) -> list[Any]:
    """Read a JSON fixture using its explicit path, independent of CWD."""
    fixture_path = Path(path)
    if not fixture_path.is_file():
        raise DataLoadError(f"fixture file not found: {fixture_path}")
    try:
        with fixture_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"invalid fixture JSON in {fixture_path}: {exc}") from exc
    except OSError as exc:
        raise DataLoadError(f"cannot read fixture file {fixture_path}: {exc}") from exc
    return _records_from_payload(payload)


def load_flight_offers(
    path: str | Path,
    *,
    source: str = "mvp-fixture",
    source_url: Optional[str] = None,
    observed_at: Optional[datetime] = None,
) -> tuple[list[FlightOffer], list[NormalizationIssue]]:
    """Load a local fixture and normalize every record independently."""
    records = load_json_records(path)
    return normalize_records(
        records,
        source=source,
        source_url=source_url,
        observed_at=observed_at,
    )
