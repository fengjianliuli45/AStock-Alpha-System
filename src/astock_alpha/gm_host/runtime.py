from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Callable

from astock_alpha.gm_host.orders import apply_target_weights
from astock_alpha.pipeline import StrategyPipeline
from astock_alpha.portfolio.signal_adapter import build_signal_targets
from astock_alpha.types import PipelineState

logger = logging.getLogger(__name__)


def load_strategy_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    # Prefer gm backtest config beside package configs/
    root = Path(__file__).resolve().parents[3]
    gm_cfg = root / "configs" / "strategy_v1_0.gm_backtest.json"
    if gm_cfg.exists():
        return gm_cfg
    return root / "configs" / "strategy_v1_0.preregistered.json"


class GmHostRuntime:
    """One rebalance: pipeline → signal targets → order_target_percent."""

    def __init__(
        self,
        config: dict[str, Any],
        pipeline: StrategyPipeline | None = None,
    ) -> None:
        self.config = config
        self.pipeline = pipeline or StrategyPipeline(config)
        portfolio = config.get("portfolio") or {}
        self.max_holdings = int(portfolio.get("max_holdings", 30))
        self.cash_floor = float(portfolio.get("cash_floor", 0.05))
        self._last_targets: dict[str, float] = {}

    @classmethod
    def from_config_path(cls, path: str | Path | None = None) -> GmHostRuntime:
        cfg_path = resolve_config_path(path)
        return cls(load_strategy_config(cfg_path))

    def amount_map(self, state: PipelineState) -> dict[str, float | None]:
        cached = state.meta.get("avg_amount_by_symbol")
        if isinstance(cached, dict):
            return {str(k): v for k, v in cached.items()}
        uni = self.pipeline.modules.get("m3_universe")
        provider = getattr(uni, "provider", None) if uni else None
        if provider is None:
            return {}
        snaps = provider.load(state.asof)
        return {s.symbol: s.avg_amount_20d for s in snaps}

    def run_rebalance(
        self,
        asof: date,
        *,
        current_symbols: list[str] | set[str] | None = None,
        order_target_percent: Callable[[str, float], None] | None = None,
    ) -> PipelineState | None:
        """Run one decision day. On pipeline failure, log and return None (skip orders)."""
        try:
            state = self.pipeline.run(asof)
            amounts = self.amount_map(state)
            build_signal_targets(
                state,
                amounts,
                max_holdings=self.max_holdings,
                cash_floor=self.cash_floor,
            )
        except Exception:
            logger.exception("gm_host: pipeline failed on %s; skip orders", asof)
            return None

        target_weights = {t.symbol: t.weight for t in state.targets}
        held = set(current_symbols or ()) | set(self._last_targets)
        if order_target_percent is not None:
            apply_target_weights(target_weights, held, order_target_percent)
        self._last_targets = dict(target_weights)
        state.meta["signal_target_weights"] = dict(target_weights)
        return state
