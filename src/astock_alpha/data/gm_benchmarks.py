from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

import pandas as pd

from astock_alpha.data.gm_api import adjust_const, ensure_token, require_gm_module

DEFAULT_HS300 = "SHSE.000300"
DEFAULT_CSI500 = "SHSE.000905"


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


class GmBenchmarkStore:
    """CSI300 / CSI500 close series from gm history (duck-types BenchmarkStore)."""

    def __init__(
        self,
        *,
        hs300: str = DEFAULT_HS300,
        csi500: str = DEFAULT_CSI500,
        lookback_calendar_days: int = 400,
        adjust: str = "prev",
        token_path: str | None = None,
        api: Any | None = None,
        history_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.hs300 = hs300
        self.csi500 = csi500
        self.lookback_calendar_days = lookback_calendar_days
        self.adjust = adjust
        self.token_path = token_path
        self._api = api
        self._history_fn = history_fn
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

    def _history(self, **kwargs: Any) -> Any:
        if self._history_fn is not None:
            return self._history_fn(**kwargs)
        api = self._ensure_api()
        return api.history(**kwargs)

    def exists(self) -> bool:
        return True

    def closes_pair(self, asof: date) -> tuple[pd.Series, pd.Series]:
        return (
            self._load_closes(self.hs300, asof),
            self._load_closes(self.csi500, asof),
        )

    def _load_closes(self, symbol: str, asof: date) -> pd.Series:
        start = (asof - timedelta(days=self.lookback_calendar_days)).isoformat()
        end = asof.isoformat() + " 16:00:00"
        adjust = self._adjust_code
        if adjust is None and self._history_fn is None:
            self._ensure_api()
            adjust = self._adjust_code
        if adjust is None:
            adjust = 1

        raw = self._history(
            symbol=symbol,
            frequency="1d",
            start_time=start,
            end_time=end,
            fields="eob,close",
            skip_suspended=False,
            adjust=adjust,
            df=True,
        )
        if isinstance(raw, pd.DataFrame):
            df = raw
        else:
            df = pd.DataFrame(raw or [])
        if df.empty:
            return pd.Series(dtype=float, name=symbol)

        if "eob" in df.columns:
            dates = [_to_date(v) for v in df["eob"]]
        elif "bob" in df.columns:
            dates = [_to_date(v) for v in df["bob"]]
        else:
            raise ValueError(f"gm history missing eob/bob for {symbol}")

        closes = pd.Series(
            pd.to_numeric(df["close"], errors="coerce").astype(float).values,
            index=pd.Index(dates),
            name=symbol,
        )
        closes = closes[closes.index.notna()]
        closes = closes[closes.index <= asof].sort_index()
        return closes
