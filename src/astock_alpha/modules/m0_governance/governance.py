from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from astock_alpha.exceptions import (
    FrozenStrategyError,
    GovernanceError,
    TradingDisabledError,
)
from astock_alpha.modules.base import StrategyModule
from astock_alpha.types import GateResult, PipelineState, PromotionMetrics, StrategyStatus


class GovernanceModule(StrategyModule):
    """Module 0: preregistration, freeze hash, promotion gate, death line, live switch."""

    name = "governance"
    module_id = "m0_governance"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._frozen_hash: str | None = None
        self._strike_count = 0
        self._status = StrategyStatus(self.config.get("status", "preregistered"))

    @classmethod
    def from_json(cls, path: str | Path) -> GovernanceModule:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        mod = cls(data)
        mod.freeze_parameters()
        return mod

    @property
    def version(self) -> str:
        return str(self.config.get("version", "unknown"))

    @property
    def strategy_name(self) -> str:
        return str(self.config.get("strategy_name", "unnamed"))

    @property
    def status(self) -> StrategyStatus:
        return self._status

    @property
    def trading_enabled(self) -> bool:
        return bool(self.config.get("trading_enabled", False))

    @property
    def parameter_hash(self) -> str | None:
        return self._frozen_hash

    def freeze_parameters(self) -> str:
        """Freeze current config into a canonical hash. Call once after load."""
        canonical = self._canonical_payload(self.config)
        self._frozen_hash = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return self._frozen_hash

    def assert_params_unchanged(self, candidate: dict[str, Any] | None = None) -> None:
        if self._frozen_hash is None:
            raise GovernanceError("parameters not frozen; call freeze_parameters() first")
        payload = candidate if candidate is not None else self.config
        digest = hashlib.sha256(
            json.dumps(self._canonical_payload(payload), sort_keys=True, ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        if digest != self._frozen_hash:
            raise GovernanceError(
                "parameter mutation detected after freeze; create a new version instead of tuning"
            )

    def assert_not_frozen(self) -> None:
        if self._status == StrategyStatus.FROZEN_PERMANENTLY:
            raise FrozenStrategyError(
                f"{self.strategy_name} {self.version} is permanently frozen; "
                "resurrect only with a new factor family + new preregistration"
            )

    def assert_trading_allowed(self) -> None:
        self.assert_not_frozen()
        self.assert_params_unchanged()
        if not self.trading_enabled:
            raise TradingDisabledError(
                "trading_enabled=false; pass promotion gate then enable manually"
            )

    def evaluate_promotion_gate(self, metrics: PromotionMetrics) -> GateResult:
        gate = self.config.get("governance", {}).get("promotion_gate", {})
        failures: list[str] = []

        min_periods = int(gate.get("min_oos_rebalance_periods", 24))
        if metrics.oos_rebalance_periods < min_periods:
            failures.append(
                f"oos_rebalance_periods {metrics.oos_rebalance_periods} < {min_periods}"
            )
        if gate.get("require_normal_cost_return_gt_0", True) and not (
            metrics.normal_cost_return > 0
        ):
            failures.append("normal_cost_return must be > 0")
        if gate.get("require_double_cost_return_ge_0", True) and not (
            metrics.double_cost_return >= 0
        ):
            failures.append("double_cost_return must be >= 0")
        max_dd = float(gate.get("max_drawdown", 0.20))
        if metrics.max_drawdown > max_dd:
            failures.append(f"max_drawdown {metrics.max_drawdown} > {max_dd}")
        min_ir = float(gate.get("min_information_ratio", 0.5))
        if metrics.information_ratio < min_ir:
            failures.append(f"information_ratio {metrics.information_ratio} < {min_ir}")
        # design: 正超额月份比例 > 55%
        min_pos = float(gate.get("min_positive_excess_month_ratio", 0.55))
        if metrics.positive_excess_month_ratio <= min_pos:
            failures.append(
                f"positive_excess_month_ratio {metrics.positive_excess_month_ratio} must be > {min_pos}"
            )
        min_roll = float(gate.get("min_rolling_12m_ir", 0.3))
        if metrics.rolling_12m_ir < min_roll:
            failures.append(f"rolling_12m_ir {metrics.rolling_12m_ir} < {min_roll}")
        max_share = float(gate.get("max_single_factor_alpha_share", 0.50))
        if metrics.max_single_factor_alpha_share > max_share:
            failures.append(
                f"max_single_factor_alpha_share {metrics.max_single_factor_alpha_share} > {max_share}"
            )
        if metrics.test_annual_excess <= 0:
            failures.append("test_annual_excess must be > 0")

        passed = len(failures) == 0
        if passed:
            self._status = StrategyStatus.PROMOTED
        return GateResult(passed=passed, failures=failures)

    def record_oos_ir(self, information_ratio: float) -> StrategyStatus:
        """Rolling OOS window strike for death line."""
        death = self.config.get("governance", {}).get("death_line", {})
        threshold = float(death.get("consecutive_oos_windows_ir_below", -0.5))
        need = int(death.get("strike_count_to_freeze", 3))
        if information_ratio < threshold:
            self._strike_count += 1
        else:
            self._strike_count = 0
        if self._strike_count >= need:
            self._status = StrategyStatus.FROZEN_PERMANENTLY
            self.config["trading_enabled"] = False
        return self._status

    def enable_trading(self, *, force: bool = False) -> None:
        """Manual live switch; requires promotion unless force (research only)."""
        self.assert_not_frozen()
        self.assert_params_unchanged()
        if self._status != StrategyStatus.PROMOTED and not force:
            raise GovernanceError("enable_trading requires PROMOTED status (or force for dry-run)")
        self.config["trading_enabled"] = True

    def disable_trading(self) -> None:
        self.config["trading_enabled"] = False

    def run(self, state: PipelineState) -> PipelineState:
        self.assert_not_frozen()
        self.assert_params_unchanged()
        state.meta["strategy_name"] = self.strategy_name
        state.meta["strategy_version"] = self.version
        state.meta["strategy_status"] = self._status.value
        state.meta["trading_enabled"] = self.trading_enabled
        state.meta["parameter_hash"] = self._frozen_hash
        if not self.trading_enabled:
            state.warnings.append("trading_enabled=false; pipeline runs in research/dry-run mode")
        return state

    @staticmethod
    def _canonical_payload(config: dict[str, Any]) -> dict[str, Any]:
        """Drop volatile runtime fields before hashing."""
        data = deepcopy(config)
        data.pop("created_at", None)
        # trading_enabled is an operational switch, not a research parameter
        data.pop("trading_enabled", None)
        # data paths / machine binding — not strategy research parameters
        data.pop("data", None)
        return data
