from __future__ import annotations

from typing import Any

from astock_alpha.modules.base import StrategyModule
from astock_alpha.types import PipelineState, Regime


class StubModule(StrategyModule):
    """Placeholder until the corresponding design module is implemented."""

    def __init__(
        self,
        module_id: str,
        name: str,
        config: dict[str, Any] | None = None,
        note: str = "",
    ) -> None:
        super().__init__(config)
        self.module_id = module_id
        self.name = name
        self.note = note or f"{module_id} stub — not implemented"

    def is_ready(self) -> bool:
        return False

    def run(self, state: PipelineState) -> PipelineState:
        state.warnings.append(self.note)
        state.meta.setdefault("stub_modules", []).append(self.module_id)
        return state


class RegimeStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m1_regime", "regime", config, "m1_regime stub: default sideways")

    def run(self, state: PipelineState) -> PipelineState:
        state = super().run(state)
        state.regime = Regime.SIDEWAYS
        mult = (self.config or {}).get("regime_multiplier", {})
        state.regime_multiplier = float(mult.get("sideways", 0.5))
        return state


class SectorStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m2_sector", "sector", config, "m2_sector stub: empty sector list")


class UniverseStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m3_universe", "universe", config, "m3_universe stub: empty universe")


class FundamentalsStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(
            "m4_fundamentals", "fundamentals", config, "m4_fundamentals stub: no scores"
        )


class TechnicalStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m5_technical", "technical", config, "m5_technical stub: gate closed")


class EntryStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m6_entry", "entry", config, "m6_entry stub: no orders")


class SizingStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m7_sizing", "sizing", config, "m7_sizing stub: no targets")


class ExitStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m8_exit", "exit", config, "m8_exit stub: no exit signals")


class PortfolioRiskStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(
            "m9_portfolio_risk",
            "portfolio_risk",
            config,
            "m9_portfolio_risk stub: no circuit breakers",
        )


class MonitorStub(StubModule):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("m10_monitor", "monitor", config, "m10_monitor stub: no IC/drift checks")
