from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

import pandas as pd

from astock_alpha.data.gm_api import adjust_const, ensure_token, require_gm_module
from astock_alpha.modules.m3_universe.snapshots import StockSnapshot

# A-share stock sec types in gm
_SEC_TYPE1_STOCK = 1010
_SEC_TYPE2_STOCK = 101001
_HISTORY_BATCH = 40  # symbols per history request (stay under 33k rows)
_AMOUNT_LOOKBACK_CAL_DAYS = 45


def _to_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    return ts.date()


def _as_records(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return []
        return data.to_dict(orient="records")
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for row in data:
            if isinstance(row, dict):
                out.append(row)
            else:
                # gm Bar / object with attrs
                out.append(
                    {
                        k: getattr(row, k)
                        for k in (
                            "symbol",
                            "eob",
                            "bob",
                            "amount",
                            "volume",
                            "close",
                            "is_st",
                            "is_suspended",
                            "sec_name",
                            "listed_date",
                            "delisted_date",
                            "trade_date",
                        )
                        if hasattr(row, k)
                    }
                )
        return out
    return []


class GmSnapshotProvider:
    """PIT StockSnapshots from 掘金 gm history / get_symbols."""

    def __init__(
        self,
        *,
        amount_window: int = 20,
        max_symbols: int | None = None,
        adjust: str = "prev",
        token_path: str | None = None,
        api: Any | None = None,
        get_symbols_fn: Callable[..., Any] | None = None,
        history_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.amount_window = amount_window
        self.max_symbols = max_symbols
        self.adjust = adjust
        self.token_path = token_path
        self._api = api
        self._get_symbols_fn = get_symbols_fn
        self._history_fn = history_fn
        self._cache: dict[date, list[StockSnapshot]] = {}
        self._token_ready = False
        self._adjust_code: int | None = None

    def _ensure_api(self) -> Any:
        if self._api is None:
            self._api = require_gm_module()
        if not self._token_ready:
            ensure_token(self._api, self.token_path)
            self._token_ready = True
        if self._adjust_code is None:
            self._adjust_code = adjust_const(self._api, self.adjust)
        return self._api

    def _get_symbols(self, **kwargs: Any) -> Any:
        if self._get_symbols_fn is not None:
            return self._get_symbols_fn(**kwargs)
        api = self._ensure_api()
        return api.get_symbols(**kwargs)

    def _history(self, **kwargs: Any) -> Any:
        if self._history_fn is not None:
            return self._history_fn(**kwargs)
        api = self._ensure_api()
        return api.history(**kwargs)

    def load(self, asof: date, symbols: list[str] | None = None) -> list[StockSnapshot]:
        if symbols is None and asof in self._cache:
            return list(self._cache[asof])

        trade_date = asof.isoformat()
        raw = self._get_symbols(
            sec_type1=_SEC_TYPE1_STOCK,
            sec_type2=_SEC_TYPE2_STOCK,
            symbols=symbols,
            skip_suspended=False,
            skip_st=False,
            trade_date=trade_date,
            df=True,
        )
        rows = _as_records(raw)
        if self.max_symbols is not None:
            rows = rows[: int(self.max_symbols)]

        meta_by_symbol: dict[str, dict[str, Any]] = {}
        for row in rows:
            sym = str(row.get("symbol") or "")
            if not sym:
                continue
            meta_by_symbol[sym] = row

        wanted = list(meta_by_symbol.keys())
        if not wanted:
            return []

        avg_amount = self._avg_amounts(wanted, asof)
        out: list[StockSnapshot] = []
        for sym in wanted:
            meta = meta_by_symbol[sym]
            listed = _to_date(meta.get("listed_date"))
            delisted = _to_date(meta.get("delisted_date"))
            listed_trading_days = None
            if listed is not None:
                # Approximate trading days (calendar*250/365); exact calendar needs heavy API.
                listed_trading_days = max(0, int((asof - listed).days * 250 / 365))

            is_delist_risk = None
            if delisted is not None:
                # Far-future sentinel (e.g. 2038) means still listed.
                is_delist_risk = delisted <= asof

            name = meta.get("sec_name")
            is_st = meta.get("is_st")
            is_suspended = meta.get("is_suspended")

            out.append(
                StockSnapshot(
                    symbol=sym,
                    asof=asof,
                    name=None if name is None else str(name),
                    is_st=None if is_st is None else bool(is_st),
                    is_delist_risk=is_delist_risk,
                    is_suspended=None if is_suspended is None else bool(is_suspended),
                    listed_trading_days=listed_trading_days,
                    avg_amount_20d=avg_amount.get(sym),
                    total_market_cap=None,
                )
            )

        if symbols is None:
            self._cache[asof] = list(out)
        return out

    def _avg_amounts(self, symbols: list[str], asof: date) -> dict[str, float | None]:
        start = (asof - timedelta(days=_AMOUNT_LOOKBACK_CAL_DAYS)).isoformat()
        end = asof.isoformat() + " 16:00:00"
        adjust = self._adjust_code
        if adjust is None and self._history_fn is None:
            self._ensure_api()
            adjust = self._adjust_code
        if adjust is None:
            adjust = 1  # ADJUST_PREV fallback for injected history in tests

        amounts: dict[str, list[float]] = {s: [] for s in symbols}
        for i in range(0, len(symbols), _HISTORY_BATCH):
            batch = symbols[i : i + _HISTORY_BATCH]
            raw = self._history(
                symbol=",".join(batch),
                frequency="1d",
                start_time=start,
                end_time=end,
                fields="symbol,eob,amount",
                skip_suspended=False,
                adjust=adjust,
                df=True,
            )
            for row in _as_records(raw):
                sym = str(row.get("symbol") or "")
                if sym not in amounts:
                    continue
                eob = _to_date(row.get("eob") or row.get("bob"))
                if eob is None or eob > asof:
                    continue
                amt = row.get("amount")
                if amt is None or (isinstance(amt, float) and pd.isna(amt)):
                    continue
                amounts[sym].append(float(amt))

        out: dict[str, float | None] = {}
        for sym, series in amounts.items():
            if not series:
                out[sym] = None
            else:
                window = series[-self.amount_window :]
                out[sym] = float(sum(window) / len(window))
        return out
