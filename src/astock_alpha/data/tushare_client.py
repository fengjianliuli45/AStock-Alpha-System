from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_TOKEN_PATH = Path.home() / ".tushare" / "token"
DEFAULT_HTTP_URL = "http://8.136.22.187:8010/"


def load_tushare_token(token_path: str | Path | None = None) -> str:
    env = os.environ.get("TUSHARE_TOKEN", "").strip()
    if env:
        return env
    path = Path(token_path) if token_path else DEFAULT_TOKEN_PATH
    if not path.exists():
        raise FileNotFoundError(f"Tushare token not found: {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError(f"Tushare token file empty: {path}")
    return token


def gm_to_ts_code(symbol: str) -> str:
    """SHSE.600000 -> 600000.SH ; SZSE.000001 -> 000001.SZ"""
    if "." not in symbol:
        return symbol
    exch, code = symbol.split(".", 1)
    exch = exch.upper()
    if exch in ("SHSE", "SH"):
        return f"{code}.SH"
    if exch in ("SZSE", "SZ"):
        return f"{code}.SZ"
    if exch in ("BJSE", "BJ"):
        return f"{code}.BJ"
    return symbol


def ts_to_gm_symbol(ts_code: str) -> str:
    code, exch = ts_code.split(".")
    exch = exch.upper()
    if exch == "SH":
        return f"SHSE.{code}"
    if exch == "SZ":
        return f"SZSE.{code}"
    if exch == "BJ":
        return f"BJSE.{code}"
    return ts_code


class TushareHttpClient:
    """Minimal Tushare-compatible HTTP client for custom proxy gateways."""

    def __init__(
        self,
        *,
        token: str | None = None,
        http_url: str = DEFAULT_HTTP_URL,
        token_path: str | Path | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.token = token or load_tushare_token(token_path)
        self.http_url = http_url if http_url.endswith("/") else http_url + "/"
        self.timeout = timeout

    def query(
        self,
        api_name: str,
        params: dict[str, Any] | None = None,
        fields: str = "",
    ) -> list[dict[str, Any]]:
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": params or {},
            "fields": fields,
        }
        req = urllib.request.Request(
            self.http_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"tushare http {e.code}: {e.read()[:200]!r}") from e

        if body.get("code") not in (0, "0", None):
            raise RuntimeError(f"tushare api error: {body.get('code')} {body.get('msg')}")

        data = body.get("data") or {}
        field_names = data.get("fields") or []
        items = data.get("items") or []
        return [dict(zip(field_names, row, strict=False)) for row in items]

    def daily_basic_total_mv_map(self, trade_date: date) -> dict[str, float]:
        """Return {GM_SYMBOL: total_market_cap_CNY}.

        Tushare `total_mv` unit is 万元 → multiply by 1e4.
        """
        rows = self.query(
            "daily_basic",
            params={"trade_date": trade_date.strftime("%Y%m%d")},
            fields="ts_code,trade_date,total_mv,circ_mv",
        )
        out: dict[str, float] = {}
        for row in rows:
            ts_code = row.get("ts_code")
            mv = row.get("total_mv")
            if not ts_code or mv is None:
                continue
            try:
                out[ts_to_gm_symbol(str(ts_code))] = float(mv) * 10_000.0
            except (TypeError, ValueError):
                continue
        return out
