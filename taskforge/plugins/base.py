from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    @abstractmethod
    async def on_load(self, app_context: dict[str, Any]) -> None:
        """Register extensions through the explicit worker context."""

    async def on_unload(self) -> None:
        """Release extension resources."""
        return None
