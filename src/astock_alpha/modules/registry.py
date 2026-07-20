from __future__ import annotations

from typing import Any

from astock_alpha.data.providers import build_snapshot_provider
from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m0_governance import GovernanceModule
from astock_alpha.data.benchmarks import BenchmarkStore
from astock_alpha.modules.m1_regime import RegimeModule
from astock_alpha.modules.m3_universe import UniverseModule
from astock_alpha.modules.m2_market_environment.environment import (
    MarketEnvironmentModule,
)
from astock_alpha.modules.stubs import (
    EntryStub,
    ExitStub,
    FundamentalsStub,
    MonitorStub,
    PortfolioRiskStub,
    SectorStub,
    SizingStub,
    TechnicalStub,
)


def build_default_modules(config: dict[str, Any]) -> dict[str, StrategyModule]:
    """Wire modules in design order. m0 + m3 implemented; others stubbed."""
    mods_cfg = config.get("modules", {})

    def enabled(mid: str) -> bool:
        return bool(mods_cfg.get(mid, {}).get("enabled", True))

    modules: dict[str, StrategyModule] = {}
    if enabled("m0_governance"):
        modules["m0_governance"] = GovernanceModule(config)
        modules["m0_governance"].freeze_parameters()
    if enabled("m1_regime"):
        data = config.get("data") or {}
        root = data.get("benchmarks_root")
        store = BenchmarkStore(root) if root else None
        modules["m1_regime"] = RegimeModule(config, store=store)
    if enabled("m2_sector"):
        modules["m2_sector"] = SectorStub(config)
    if enabled("m2_market_environment"):
        modules["m2_market_environment"] = MarketEnvironmentModule(config)
    if enabled("m3_universe"):
        provider = build_snapshot_provider(config)
        modules["m3_universe"] = UniverseModule(config, provider=provider)
    if enabled("m4_fundamentals"):
        modules["m4_fundamentals"] = FundamentalsStub(config)
    if enabled("m5_technical"):
        modules["m5_technical"] = TechnicalStub(config)
    if enabled("m7_sizing"):
        modules["m7_sizing"] = SizingStub(config)
    if enabled("m6_entry"):
        modules["m6_entry"] = EntryStub(config)
    if enabled("m8_exit"):
        modules["m8_exit"] = ExitStub(config)
    if enabled("m9_portfolio_risk"):
        modules["m9_portfolio_risk"] = PortfolioRiskStub(config)
    if enabled("m10_monitor"):
        modules["m10_monitor"] = MonitorStub(config)
    return modules


# Pipeline execution order (rebalance day morning → close → next open monitoring)
PIPELINE_ORDER = [
    "m0_governance",
    "m1_regime",
    "m2_market_environment",  # 环境评级（五大维度），依赖 m1 情绪输出
    "m2_sector",
    "m3_universe",
    "m4_fundamentals",
    "m5_technical",
    "m7_sizing",
    "m6_entry",
    "m8_exit",
    "m9_portfolio_risk",
    "m10_monitor",
]
