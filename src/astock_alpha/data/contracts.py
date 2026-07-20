"""Point-in-time data contracts required by the design doc.

Implementations must refuse future information. Adapters land in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True, frozen=True)
class PitFundamentalRow:
    symbol: str
    report_period: date
    published_at: date
    # fields filled by adapters later


@dataclass(slots=True, frozen=True)
class IndustryMembership:
    symbol: str
    industry: str
    effective_from: date
    effective_to: date | None = None


def assert_pit_fundamental(asof: date, published_at: date, report_period: date) -> None:
    if published_at > asof:
        raise ValueError("look-ahead: published_at after asof")
    if report_period > asof:
        raise ValueError("look-ahead: report_period after asof")
