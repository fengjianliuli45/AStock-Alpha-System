"""掘金策略入口：在终端中指向本模块，或运行 strategies/gm_astock_alpha.py。"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from astock_alpha.data.gm_api import load_token
from astock_alpha.gm_host.runtime import GmHostRuntime, resolve_config_path

logger = logging.getLogger(__name__)

_RUNTIME: GmHostRuntime | None = None


def _bar_asof(bar: Any) -> date:
    eob = getattr(bar, "eob", None)
    if eob is None and isinstance(bar, dict):
        eob = bar.get("eob") or bar.get("bob")
    if hasattr(eob, "date"):
        return eob.date()
    if isinstance(eob, date):
        return eob
    raise ValueError(f"cannot parse bar date from {bar!r}")


def _current_symbols(context: Any) -> list[str]:
    try:
        account = context.account()
        positions = account.positions()
    except Exception:
        try:
            from gm.api import get_position  # type: ignore

            positions = get_position()
        except Exception:
            return []
    out: list[str] = []
    for pos in positions or []:
        if isinstance(pos, dict):
            sym = pos.get("symbol")
            vol = pos.get("volume") or pos.get("available") or 0
        else:
            sym = getattr(pos, "symbol", None)
            vol = getattr(pos, "volume", 0) or getattr(pos, "available", 0)
        if sym and float(vol) > 0:
            out.append(str(sym))
    return out


def _make_order_fn(gm_api: Any):
    # gm.api.order_target_percent requires positional-compatible side/type.
    side = int(getattr(gm_api, "PositionSide_Long", 1))
    order_type = int(getattr(gm_api, "OrderType_Market", 2))

    def order_target_percent(symbol: str, percent: float) -> None:
        gm_api.order_target_percent(
            symbol,
            float(percent),
            side,
            order_type,
        )

    return order_target_percent


def init(context: Any) -> None:
    global _RUNTIME
    cfg_path = os.environ.get("ASTOCK_ALPHA_CONFIG") or getattr(
        context, "astock_config", None
    )
    path = resolve_config_path(cfg_path)
    _RUNTIME = GmHostRuntime.from_config_path(path)
    context.astock_runtime = _RUNTIME
    context.astock_config_path = str(path)

    host = (_RUNTIME.config.get("gm_host") or {}) if _RUNTIME else {}
    clock = str(host.get("clock_symbol", "SHSE.000300"))
    freq = str(host.get("frequency", "1d"))

    from gm.api import subscribe  # type: ignore

    subscribe(symbols=clock, frequency=freq)
    logger.info("astock_alpha gm_host init config=%s clock=%s", path, clock)


def on_bar(context: Any, bars: list[Any]) -> None:
    runtime: GmHostRuntime | None = getattr(context, "astock_runtime", None) or _RUNTIME
    if runtime is None or not bars:
        return
    try:
        asof = _bar_asof(bars[0])
    except Exception:
        logger.exception("gm_host: bad bar timestamp")
        return

    from gm import api as gm_api  # type: ignore

    runtime.run_rebalance(
        asof,
        current_symbols=_current_symbols(context),
        order_target_percent=_make_order_fn(gm_api),
    )


def on_error(context: Any, code: Any, info: Any) -> None:
    logger.error("gm_host on_error code=%s info=%s", code, info)


def run_backtest(
    *,
    config_path: str | Path | None = None,
    strategy_id: str | None = None,
    token: str | None = None,
    filename: str | None = None,
) -> None:
    """Programmatic MODE_BACKTEST launcher (requires gm + terminal)."""
    from gm.api import ADJUST_PREV, MODE_BACKTEST, run  # type: ignore

    cfg_path = resolve_config_path(config_path)
    cfg = GmHostRuntime.from_config_path(cfg_path).config
    host = cfg.get("gm_host") or {}
    costs = cfg.get("costs") or {}
    data = cfg.get("data") or {}

    tok = token or os.environ.get("GM_TOKEN") or load_token(data.get("gm_token_path"))
    if not tok:
        raise RuntimeError(
            "gm token missing: set GM_TOKEN, data.gm_token_path, or pass token="
        )

    start = host.get("backtest_start", "2021-01-01")
    end = host.get("backtest_end", "2025-12-31")
    if " " not in str(start):
        start = f"{start} 09:00:00"
    if " " not in str(end):
        end = f"{end} 16:00:00"

    entry_path = Path(filename) if filename else Path(__file__).resolve()
    # gm.run uses os.path.commonprefix against forward-slash sys.path entries;
    # Windows backslashes collapse the shared prefix to "D:" and break import.
    entry_file = str(entry_path.resolve()).replace("\\", "/")
    src_root = str(Path(__file__).resolve().parents[2])
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    run(
        strategy_id=strategy_id or host.get("strategy_id") or "astock_alpha_gm",
        filename=entry_file,
        mode=MODE_BACKTEST,
        token=tok,
        backtest_start_time=start,
        backtest_end_time=end,
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=float(host.get("initial_cash", 1_000_000)),
        backtest_commission_ratio=float(costs.get("commission_rate", 0.0003)),
        backtest_slippage_ratio=float(costs.get("base_slippage", 0.002)),
    )


if __name__ == "__main__":
    run_backtest()
