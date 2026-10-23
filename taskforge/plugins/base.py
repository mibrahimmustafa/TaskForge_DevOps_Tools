from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    id: str = "base"
    name: str = "Base Plugin"
    version: str = "0.1.0"
    description: str = ""
    icon: str = "🔌"
    plugin_type: str = "general"
    enabled: bool = True

    @abstractmethod
    async def on_load(self, app_context: dict[str, Any]) -> None:
        pass
