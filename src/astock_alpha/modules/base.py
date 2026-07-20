from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from astock_alpha.types import PipelineState


class StrategyModule(ABC):
    """Base class for design modules 0–10."""

    name: str = "base"
    module_id: str = "base"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def run(self, state: PipelineState) -> PipelineState:
        """Transform pipeline state; must be idempotent for the same asof+inputs."""

    def is_ready(self) -> bool:
        """False for stubs that must not be used in promotion/live."""
        return True
