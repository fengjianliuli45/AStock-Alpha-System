from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class Regime(str, Enum):
    BULL = "bull"
    SIDEWAYS = "sideways"
    SIDEWAYS_LOWVOL = "sideways_lowvol"
    SIDEWAYS_HIGHVOL = "sideways_highvol"
    BEAR = "bear"
    PANIC = "panic"


class StrategyStatus(str, Enum):
    PREREGISTERED = "preregistered"
    RESEARCH = "research"
    PROMOTED = "promoted"
    FROZEN_PERMANENTLY = "frozen_permanently"
    LIVE_DRIFT_WARNING = "live_drift_warning"
    LIVE_DRIFT_SHUTDOWN = "live_drift_shutdown"


@dataclass(slots=True)
class BarContext:
    """Point-in-time market context for one decision date."""

    asof: date
    symbols: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Candidate:
    symbol: str
    industry: str | None = None
    fundamental_score: float = 0.0
    technical_gate: float = 0.0
    sector_score: float = 0.0
    composite_score: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TargetPosition:
    symbol: str
    weight: float
    reason: str = ""


@dataclass(slots=True)
class OrderIntent:
    symbol: str
    side: str  # buy | sell
    quantity: int
    limit_price: float | None = None
    reason: str = ""
    blocked: bool = False
    block_reason: str = ""


@dataclass(slots=True)
class ExitSignal:
    symbol: str
    action: str  # sell_all | sell_partial
    fraction: float = 1.0
    reason: str = ""
    priority: int = 99


@dataclass(slots=True)
class PipelineState:
    """Shared state flowing through modules on a rebalance / monitoring pass."""

    asof: date
    regime: Regime = Regime.SIDEWAYS
    regime_multiplier: float = 0.5
    universe: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    targets: list[TargetPosition] = field(default_factory=list)
    entry_orders: list[OrderIntent] = field(default_factory=list)
    exit_signals: list[ExitSignal] = field(default_factory=list)
    incomplete_filters: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromotionMetrics:
    """Inputs for Module 0 promotion gate (filled by backtest later)."""

    oos_rebalance_periods: int = 0
    normal_cost_return: float = 0.0
    double_cost_return: float = 0.0
    max_drawdown: float = 0.0
    information_ratio: float = 0.0
    positive_excess_month_ratio: float = 0.0
    rolling_12m_ir: float = 0.0
    max_single_factor_alpha_share: float = 0.0
    test_annual_excess: float = 0.0


@dataclass(slots=True)
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
