from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from astock_alpha.modules.m3_universe.snapshots import StockSnapshot


@dataclass(slots=True)
class UniverseFilterConfig:
    min_listed_trading_days: int = 120
    min_avg_amount_20d: float = 1e8  # 1 亿
    min_total_market_cap: float = 5e9  # 50 亿
    max_unlock_pct_next_30d: float = 0.05
    max_goodwill_to_equity: float = 0.30
    max_quarter_ni_yoy_drop: float = -0.50  # <= this → fail
    # soft
    max_pledge_ratio: float = 0.50
    min_analyst_coverage: int = 3
    apply_soft_filters: bool = True
    enforce_suspension: bool = True
    limit_up_in_universe: bool = False

    @classmethod
    def from_strategy_config(cls, config: dict[str, Any]) -> UniverseFilterConfig:
        u = config.get("universe", {})
        return cls(
            min_listed_trading_days=int(u.get("min_listed_trading_days", 120)),
            min_avg_amount_20d=float(u.get("min_avg_amount_20d", 1e8)),
            min_total_market_cap=float(u.get("min_total_market_cap", 5e9)),
            max_unlock_pct_next_30d=float(u.get("max_unlock_pct_next_30d", 0.05)),
            max_goodwill_to_equity=float(u.get("max_goodwill_to_equity", 0.30)),
            max_quarter_ni_yoy_drop=float(u.get("max_quarter_ni_yoy_drop", -0.50)),
            max_pledge_ratio=float(u.get("max_pledge_ratio", 0.50)),
            min_analyst_coverage=int(u.get("min_analyst_coverage", 3)),
            apply_soft_filters=bool(u.get("apply_soft_filters", True)),
            enforce_suspension=bool(u.get("enforce_suspension", True)),
            limit_up_in_universe=bool(u.get("limit_up_in_universe", False)),
        )


@dataclass(slots=True)
class FilterDecision:
    passed: bool
    reject_reasons: list[str] = field(default_factory=list)
    incomplete_filters: list[str] = field(default_factory=list)


def _name_looks_st(name: str | None) -> bool:
    if not name:
        return False
    upper = name.upper()
    return "ST" in upper or "退" in name


def _fundamentals_pit_ok(snap: StockSnapshot) -> bool:
    """Financial hard filters only apply when fundamentals_asof is known and <= asof."""
    if snap.fundamentals_asof is None:
        return False
    return snap.fundamentals_asof <= snap.asof


def evaluate_stock(snap: StockSnapshot, cfg: UniverseFilterConfig) -> FilterDecision:
    """AND hard filters. Missing data → incomplete, do not false-reject."""
    rejects: list[str] = []
    incomplete: list[str] = []

    # --- hard ---
    # ST: prefer per-day boolean; name is same-day fallback only (never rewrite history)
    st_flag = snap.is_st
    if st_flag is None and snap.name is not None:
        st_flag = _name_looks_st(snap.name)
    if st_flag is True or snap.is_delist_risk is True:
        rejects.append("st_or_delist_risk")
    elif st_flag is None and snap.is_delist_risk is None:
        incomplete.append("st_or_delist_risk")

    if cfg.enforce_suspension:
        if snap.is_suspended is True:
            rejects.append("suspended")
        elif snap.is_suspended is None:
            incomplete.append("suspended")

    if snap.listed_trading_days is None:
        incomplete.append("listed_trading_days")
    elif snap.listed_trading_days < cfg.min_listed_trading_days:
        rejects.append("listed_trading_days")

    if snap.avg_amount_20d is None:
        incomplete.append("avg_amount_20d")
    elif snap.avg_amount_20d < cfg.min_avg_amount_20d:
        rejects.append("avg_amount_20d")

    if snap.total_market_cap is None:
        incomplete.append("total_market_cap")
    elif snap.total_market_cap < cfg.min_total_market_cap:
        rejects.append("total_market_cap")

    # Limit-up belongs to entry day (m6) by default
    if cfg.limit_up_in_universe:
        if snap.buy_blocked_limit_up is True:
            rejects.append("buy_blocked_limit_up")
        elif snap.buy_blocked_limit_up is None:
            incomplete.append("buy_blocked_limit_up")

    if snap.unlock_pct_next_30d is None:
        incomplete.append("unlock_pct_next_30d")
    elif snap.unlock_pct_next_30d > cfg.max_unlock_pct_next_30d:
        rejects.append("unlock_pct_next_30d")

    if snap.ctrl_shareholder_reduce_60d is None:
        incomplete.append("ctrl_shareholder_reduce_60d")
    elif snap.ctrl_shareholder_reduce_60d is True:
        rejects.append("ctrl_shareholder_reduce_60d")

    if not _fundamentals_pit_ok(snap):
        incomplete.append("fundamentals_asof")
        # do not apply earnings/goodwill rejects without PIT stamp
    else:
        if snap.worst_quarter_ni_yoy_180d is None:
            incomplete.append("worst_quarter_ni_yoy_180d")
        elif snap.worst_quarter_ni_yoy_180d <= cfg.max_quarter_ni_yoy_drop:
            rejects.append("earnings_collapse")

        if snap.goodwill_to_equity is None:
            incomplete.append("goodwill_to_equity")
        elif snap.goodwill_to_equity > cfg.max_goodwill_to_equity:
            rejects.append("goodwill_to_equity")

    # --- soft ---
    if cfg.apply_soft_filters:
        if snap.pledge_ratio is None:
            incomplete.append("pledge_ratio")
        elif snap.pledge_ratio > cfg.max_pledge_ratio:
            rejects.append("pledge_ratio")

        if snap.has_fraud_or_violation_5y is None:
            incomplete.append("fraud_or_violation_5y")
        elif snap.has_fraud_or_violation_5y is True:
            rejects.append("fraud_or_violation_5y")

        if snap.non_standard_audit is None:
            incomplete.append("non_standard_audit")
        elif snap.non_standard_audit is True:
            rejects.append("non_standard_audit")

        if snap.analyst_coverage is None:
            incomplete.append("analyst_coverage")
        elif snap.analyst_coverage < cfg.min_analyst_coverage:
            incomplete.append("analyst_coverage_low")

    return FilterDecision(
        passed=len(rejects) == 0,
        reject_reasons=rejects,
        incomplete_filters=incomplete,
    )
