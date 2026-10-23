"""Explicit registry: only installed, administrator-selected extensions may be loaded."""

from importlib.metadata import entry_points

from taskforge.plugins.base import BasePlugin


class PluginLoader:
    def __init__(self):
        self.plugins: dict[str, BasePlugin] = {}

    async def load(self, names: list[str], context: dict):
        available = {entry.name: entry for entry in entry_points(group="taskforge.plugins")}
        for name in names:
            if name not in available:
                raise ValueError(f"Plugin is not installed: {name}")
            instance = available[name].load()()
            if not isinstance(instance, BasePlugin):
                raise TypeError(f"Invalid plugin: {name}")
            await instance.on_load(context)
            self.plugins[name] = instance

    async def close(self):
        for instance in reversed(list(self.plugins.values())):
            await instance.on_unload()
        self.plugins.clear()


plugin_loader = PluginLoader()
