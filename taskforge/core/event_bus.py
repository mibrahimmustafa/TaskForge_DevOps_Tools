import asyncio
from typing import Callable, Any
from taskforge.core.logging import logger

class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[..., Any]]] = {}

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        if event_name in self._subscribers:
            self._subscribers[event_name] = [cb for cb in self._subscribers[event_name] if cb != callback]

    async def emit(self, event_name: str, **payload: Any) -> None:
        callbacks = self._subscribers.get(event_name, []) + self._subscribers.get("*", [])
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event_name=event_name, **payload)
                else:
                    cb(event_name=event_name, **payload)
            except Exception as e:
                logger.error("event_bus_callback_failed", event=event_name, error=str(e))

event_bus = EventBus()
