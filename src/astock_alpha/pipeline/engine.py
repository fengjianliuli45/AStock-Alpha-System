from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m0_governance import GovernanceModule
from astock_alpha.modules.registry import PIPELINE_ORDER, build_default_modules
from astock_alpha.types import PipelineState


class StrategyPipeline:
    """Orchestrates modules 0–10 for one as-of decision pass."""

    def __init__(
        self,
        config: dict[str, Any],
        modules: dict[str, StrategyModule] | None = None,
    ) -> None:
        self.config = config
        self.modules = modules or build_default_modules(config)
        gov = self.modules.get("m0_governance")
        self.governance = gov if isinstance(gov, GovernanceModule) else None

    @classmethod
    def from_config_path(cls, path: str | Path) -> StrategyPipeline:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data)

    def readiness(self) -> dict[str, bool]:
        return {mid: mod.is_ready() for mid, mod in self.modules.items()}

    def run(self, asof: date) -> PipelineState:
        state = PipelineState(asof=asof)
        for mid in PIPELINE_ORDER:
            mod = self.modules.get(mid)
            if mod is None:
                continue
            state = mod.run(state)
        state.meta["readiness"] = self.readiness()
        return state

    def summary(self, state: PipelineState) -> dict[str, Any]:
        return {
            "asof": state.asof.isoformat(),
            "regime": state.regime.value,
            "regime_multiplier": state.regime_multiplier,
            "universe_size": len(state.universe),
            "candidates": len(state.candidates),
            "targets": len(state.targets),
            "entry_orders": len(state.entry_orders),
            "exit_signals": len(state.exit_signals),
            "warnings": state.warnings,
            "strategy": {
                "name": state.meta.get("strategy_name"),
                "version": state.meta.get("strategy_version"),
                "status": state.meta.get("strategy_status"),
                "trading_enabled": state.meta.get("trading_enabled"),
                "parameter_hash": state.meta.get("parameter_hash"),
            },
            "readiness": state.meta.get("readiness", {}),
        }
