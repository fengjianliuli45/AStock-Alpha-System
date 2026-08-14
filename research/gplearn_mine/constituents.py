from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path
from typing import Any


def _to_gm_symbol(code: str) -> str:
    code = str(code).strip().upper()
    if code.startswith(("SHSE.", "SZSE.")):
        return code
    if "." in code:
        num, exch = code.split(".", 1)
        exch = exch.upper()
        if exch in {"SH", "SSE"}:
            return f"SHSE.{num.zfill(6)}"
        if exch in {"SZ", "SZSE"}:
            return f"SZSE.{num.zfill(6)}"
    num = code.zfill(6)
    if num.startswith(("5", "6", "9")):
        return f"SHSE.{num}"
    return f"SZSE.{num}"


def load_constituents_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"constituents file not found: {path}")
    if path.suffix.lower() == ".parquet":
        import pandas as pd

        df = pd.read_parquet(path)
        col = "symbol" if "symbol" in df.columns else df.columns[0]
        return sorted({_to_gm_symbol(x) for x in df[col].dropna().astype(str)})

    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"constituents file is empty: {path}")
    # CSV with header or plain one-symbol-per-line
    lines = text.splitlines()
    symbols: list[str] = []
    if "," in lines[0] or "\t" in lines[0]:
        reader = csv.DictReader(lines)
        if reader.fieldnames and "symbol" in reader.fieldnames:
            for row in reader:
                if row.get("symbol"):
                    symbols.append(_to_gm_symbol(row["symbol"]))
        else:
            # first column
            reader2 = csv.reader(lines)
            header = next(reader2, None)
            for row in reader2:
                if row:
                    symbols.append(_to_gm_symbol(row[0]))
            if header and header[0].lower() not in {"symbol", "code", "ts_code"}:
                symbols.insert(0, _to_gm_symbol(header[0]))
    else:
        symbols = [_to_gm_symbol(x) for x in lines if x.strip()]
    out = sorted(set(symbols))
    if not out:
        raise ValueError(f"no symbols parsed from {path}")
    return out


def fetch_csi300_baostock() -> list[str]:
    """Fetch current HS300 constituents via baostock (static snapshot, not PIT)."""
    try:
        import baostock as bs  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "baostock is required to fetch CSI300 constituents. "
            "pip install baostock  (or pass --constituents PATH)"
        ) from exc
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")
    try:
        rs = bs.query_hs300_stocks()
        rows: list[list[str]] = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()
    # row: updateDate, code (sh.600000), code_name
    symbols: list[str] = []
    for row in rows:
        code = row[1] if len(row) > 1 else ""
        if code.startswith("sh."):
            symbols.append("SHSE." + code.split(".", 1)[1])
        elif code.startswith("sz."):
            symbols.append("SZSE." + code.split(".", 1)[1])
    out = sorted(set(symbols))
    if len(out) < 50:
        raise RuntimeError(f"baostock HS300 returned too few symbols: {len(out)}")
    return out


def fetch_csi300_eastmoney(timeout: float = 30.0) -> list[str]:
    """Fallback: paginated Eastmoney BK0500 board (may be incomplete)."""
    symbols: list[str] = []
    for pn in range(1, 6):
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get?"
            f"pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&"
            "fs=b:BK0500+f:!50&fields=f12,f13,f14"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AStock-Alpha-research/0.1)",
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        diff = (payload.get("data") or {}).get("diff") or []
        if not diff:
            break
        for row in diff:
            code = str(row.get("f12", "")).zfill(6)
            market = row.get("f13")  # 0 SZ, 1 SH
            if market == 1:
                symbols.append(f"SHSE.{code}")
            else:
                symbols.append(f"SZSE.{code}")
    out = sorted(set(symbols))
    if len(out) < 50:
        raise RuntimeError(
            f"eastmoney CSI300 fetch returned too few symbols: {len(out)}"
        )
    return out


def try_fetch_csi300_gm(token_path: Path | None = None) -> list[str]:
    """Optional gm path; returns empty list on any failure."""
    try:
        from gm import api as gm_api  # type: ignore
    except Exception:
        return []
    try:
        if token_path and token_path.exists():
            token = token_path.read_text(encoding="utf-8-sig").strip()
            if token:
                gm_api.set_token(token)
        df = gm_api.stk_get_index_constituents(index="SHSE.000300")
        if df is None or len(df) == 0:
            return []
        col = "symbol" if "symbol" in df.columns else df.columns[0]
        return sorted({_to_gm_symbol(x) for x in df[col].astype(str)})
    except Exception:
        return []


def resolve_constituents(
    path: Path | None,
    *,
    allow_fetch: bool = True,
    prefer_gm: bool = True,
    token_path: Path | None = Path(r"C:\Users\123\.myquant\token"),
) -> tuple[list[str], dict[str, Any]]:
    meta: dict[str, Any] = {"pit": False, "note": "static/recent constituents snapshot"}
    if path is not None and path.exists():
        symbols = load_constituents_file(path)
        meta.update({"source": "file", "path": str(path), "n": len(symbols)})
        return symbols, meta

    if allow_fetch and prefer_gm:
        symbols = try_fetch_csi300_gm(token_path)
        if symbols:
            meta.update({"source": "gm", "index": "SHSE.000300", "n": len(symbols)})
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                _write_symbols_csv(path, symbols)
                meta["saved_to"] = str(path)
            return symbols, meta

    if allow_fetch:
        try:
            symbols = fetch_csi300_baostock()
            meta.update({"source": "baostock", "index": "hs300", "n": len(symbols)})
        except Exception as bao_exc:
            try:
                symbols = fetch_csi300_eastmoney()
                meta.update(
                    {
                        "source": "eastmoney",
                        "board": "BK0500",
                        "n": len(symbols),
                        "baostock_error": str(bao_exc),
                    }
                )
            except Exception as em_exc:
                raise FileNotFoundError(
                    "CSI300 constituents unavailable. Pass --constituents PATH "
                    f"(baostock: {bao_exc}; eastmoney: {em_exc})"
                ) from em_exc
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_symbols_csv(path, symbols)
            meta["saved_to"] = str(path)
        return symbols, meta

    raise FileNotFoundError(
        "CSI300 constituents unavailable. Pass --constituents PATH or allow network fetch."
    )


def _write_symbols_csv(path: Path, symbols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol"])
        for s in symbols:
            w.writerow([s])
