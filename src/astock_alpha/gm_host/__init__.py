"""掘金终端宿主：回测生命周期内调用本库 StrategyPipeline。"""

from astock_alpha.gm_host.runtime import GmHostRuntime, load_strategy_config

__all__ = ["GmHostRuntime", "load_strategy_config"]
