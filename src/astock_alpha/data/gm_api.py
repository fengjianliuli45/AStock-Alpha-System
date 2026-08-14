from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol


class GmApi(Protocol):
    """Minimal gm surface used by providers (injectable for tests)."""

    def set_token(self, token: str) -> None: ...

    def get_symbols(self, **kwargs: Any) -> Any: ...

    def history(self, **kwargs: Any) -> Any: ...


def require_gm_module() -> Any:
    try:
        from gm import api as gm_api  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "gm SDK is not installed. Install with: pip install 'astock-alpha-system[gm]' "
            "or pip install gm (requires 掘金终端)."
        ) from exc
    return gm_api


def load_token(token_path: str | Path | None) -> str | None:
    if not token_path:
        return None
    path = Path(token_path)
    if not path.exists():
        raise FileNotFoundError(f"gm token file not found: {path}")
    token = path.read_text(encoding="utf-8-sig").strip()
    if not token:
        raise ValueError(f"gm token file is empty: {path}")
    return token


def ensure_token(api: Any, token_path: str | Path | None) -> None:
    """Call set_token when a path is configured; otherwise rely on terminal login."""
    token = load_token(token_path)
    if token:
        api.set_token(token)


def adjust_const(api: Any, adjust: str) -> int:
    key = (adjust or "prev").lower()
    mapping = {
        "none": getattr(api, "ADJUST_NONE", 0),
        "prev": getattr(api, "ADJUST_PREV", 1),
        "post": getattr(api, "ADJUST_POST", 2),
    }
    if key not in mapping:
        raise ValueError(f"unknown data.gm_adjust: {adjust}")
    return int(mapping[key])


CallableHistory = Callable[..., Any]
CallableGetSymbols = Callable[..., Any]
