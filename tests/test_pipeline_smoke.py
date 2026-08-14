from __future__ import annotations

from datetime import date
from pathlib import Path

from astock_alpha.pipeline import StrategyPipeline

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "strategy_v1_0.preregistered.json"


def test_pipeline_runs_dry():
    pipe = StrategyPipeline.from_config_path(CONFIG)
    state = pipe.run(date(2026, 7, 18))
    summary = pipe.summary(state)
    assert summary["strategy"]["version"] == "v1.0"
    assert summary["strategy"]["trading_enabled"] is False
    assert summary["strategy"]["parameter_hash"]
    assert pipe.readiness()["m0_governance"] is True
    # m3 ready only when configured a_share_5y root exists on this machine
    assert pipe.readiness()["m8_exit"] is False
    assert "m0_governance" in pipe.readiness()
