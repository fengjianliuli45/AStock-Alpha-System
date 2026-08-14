class StrategyError(Exception):
    """Base error for the strategy system."""


class GovernanceError(StrategyError):
    """Raised when governance / preregistration rules are violated."""


class FrozenStrategyError(GovernanceError):
    """Strategy hit death line and is permanently frozen."""


class TradingDisabledError(GovernanceError):
    """Live trading attempted while trading_enabled is false."""


class ModuleNotReadyError(StrategyError):
    """Module is stubbed or incomplete for the requested operation."""
