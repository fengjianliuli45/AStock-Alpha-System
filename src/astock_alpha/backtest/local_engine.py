from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from astock_alpha.data.a_share_5y import AShare5ySnapshotProvider
from astock_alpha.data.benchmarks import BenchmarkStore
from astock_alpha.gm_host.runtime import GmHostRuntime
from astock_alpha.modules.m3_universe import UniverseModule
from astock_alpha.modules.registry import build_default_modules
from astock_alpha.pipeline import StrategyPipeline


@dataclass
class LocalBacktestResult:
    nav: pd.Series
    positions_log: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_csv(self, path: str | Path) -> None:
        self.nav.to_frame("nav").to_csv(path)


class LocalBacktestEngine:
    """Daily/weekly signal backtest on local a_share_5y + close-to-close marks.

    Uses the same signal adapter as the 掘金 host. Matching is research-grade
    (not 掘金 exchange matching); costs applied as simple turnover haircut.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        data = config.get("data") or {}
        root = data.get("a_share_5y_root")
        if not root:
            raise ValueError("data.a_share_5y_root required for local backtest")
        max_symbols = data.get("max_symbols")
        self.provider = AShare5ySnapshotProvider(
            root,
            amount_window=int(data.get("amount_window", 20)),
            max_symbols=int(max_symbols) if max_symbols is not None else None,
        )
        modules = build_default_modules(config)
        if "m3_universe" in modules:
            modules["m3_universe"] = UniverseModule(config, provider=self.provider)
        # Force local benchmarks even if config says gm
        if "m1_regime" in modules:
            from astock_alpha.modules.m1_regime import RegimeModule

            broot = data.get("benchmarks_root")
            store = BenchmarkStore(broot) if broot else None
            modules["m1_regime"] = RegimeModule(config, store=store)
        pipe = StrategyPipeline(config, modules=modules)
        self.runtime = GmHostRuntime(config, pipeline=pipe)
        costs = config.get("costs") or {}
        self.commission = float(costs.get("commission_rate", 0.0003))
        self.stamp = float(costs.get("stamp_tax_sell", 0.0005))
        self.slippage = float(costs.get("base_slippage", 0.002))

    @classmethod
    def from_config_path(cls, path: str | Path) -> LocalBacktestEngine:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        # Local engine always uses a_share_5y panel + local benchmarks.
        data = dict(cfg.get("data") or {})
        data["provider"] = "a_share_5y"
        data["enrich_market_cap"] = False  # avoid per-day HTTP in long backtests
        cfg["data"] = data
        return cls(cfg)

    def trading_dates(self, start: date, end: date) -> list[date]:
        data = self.config.get("data") or {}
        root = Path(data["benchmarks_root"])
        hs = pd.read_parquet(root / "CSI300.parquet")
        hs["date"] = pd.to_datetime(hs["date"]).dt.date
        days = sorted(d for d in hs["date"] if start <= d <= end)
        return days

    def run(
        self,
        start: date,
        end: date,
        *,
        initial_cash: float = 1_000_000.0,
        rebalance_every: int = 1,
    ) -> LocalBacktestResult:
        days = self.trading_dates(start, end)
        if not days:
            raise ValueError(f"no trading dates in [{start}, {end}]")

        cash = float(initial_cash)
        holdings: dict[str, float] = {}  # symbol -> shares
        nav_rows: list[tuple[date, float]] = []
        pos_log: list[dict[str, Any]] = []
        last_targets: dict[str, float] = {}

        n_days = len(days)
        for i, asof in enumerate(days):
            # Mark-to-market
            equity = cash
            for sym, shares in list(holdings.items()):
                px = self.provider.close_on(sym, asof)
                if px is None:
                    continue
                equity += shares * px
            nav_rows.append((asof, equity))

            if i % rebalance_every != 0:
                continue
            if equity <= 0:
                continue

            if i == 0 or (i // rebalance_every) % 20 == 0:
                print(
                    f"[local_bt] {i+1}/{n_days} asof={asof} nav={equity:,.0f} "
                    f"holdings={len(holdings)}",
                    flush=True,
                )

            state = self.runtime.run_rebalance(asof, current_symbols=list(holdings))
            if state is None:
                continue
            targets = {t.symbol: t.weight for t in state.targets}

            # Flatten names leaving book
            for sym in list(holdings):
                if sym not in targets:
                    px = self.provider.close_on(sym, asof)
                    if px is None:
                        continue
                    proceeds = holdings[sym] * px
                    cost = proceeds * (self.commission + self.stamp + self.slippage)
                    cash += proceeds - cost
                    del holdings[sym]

            # Target weights → shares at today's close (research fill)
            for sym, weight in targets.items():
                px = self.provider.close_on(sym, asof)
                if px is None or px <= 0:
                    continue
                target_value = equity * weight
                cur_shares = holdings.get(sym, 0.0)
                cur_value = cur_shares * px
                delta_value = target_value - cur_value
                if abs(delta_value) < 1.0:
                    continue
                delta_shares = delta_value / px
                trade_notional = abs(delta_shares) * px
                fee_rate = self.commission + self.slippage
                if delta_shares < 0:
                    fee_rate += self.stamp
                fee = trade_notional * fee_rate
                cash -= delta_value + fee
                holdings[sym] = cur_shares + delta_shares
                if abs(holdings[sym]) < 1e-8:
                    holdings.pop(sym, None)

            last_targets = targets
            pos_log.append(
                {
                    "asof": asof.isoformat(),
                    "nav": equity,
                    "n_holdings": len(holdings),
                    "regime": state.regime.value,
                    "regime_multiplier": state.regime_multiplier,
                    "targets": dict(last_targets),
                }
            )

        nav = pd.Series(
            {d: v for d, v in nav_rows},
            name="nav",
            dtype=float,
        ).sort_index()
        summary = _summarize(nav, initial_cash)
        summary["start"] = start.isoformat()
        summary["end"] = end.isoformat()
        summary["rebalance_every"] = rebalance_every
        summary["n_rebalances"] = len(pos_log)
        return LocalBacktestResult(nav=nav, positions_log=pos_log, summary=summary)


def _summarize(nav: pd.Series, initial: float) -> dict[str, Any]:
    if nav.empty:
        return {"error": "empty nav"}
    total_ret = float(nav.iloc[-1] / initial - 1.0)
    dd = float((nav / nav.cummax() - 1.0).min())
    # rough annualization
    n = max(len(nav) - 1, 1)
    years = n / 252.0
    ann = (1.0 + total_ret) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    daily = nav.pct_change().dropna()
    vol = float(daily.std() * (252**0.5)) if len(daily) else 0.0
    sharpe = float(ann / vol) if vol > 1e-12 else 0.0
    return {
        "final_nav": float(nav.iloc[-1]),
        "total_return": total_ret,
        "ann_return": ann,
        "max_drawdown": dd,
        "ann_vol": vol,
        "sharpe_like": sharpe,
        "n_days": int(len(nav)),
    }
