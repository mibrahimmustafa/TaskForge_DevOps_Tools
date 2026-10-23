import os
from typing import Any
from taskforge.plugins.base import BasePlugin
from taskforge.core.logging import logger

class PluginLoader:
    def __init__(self) -> None:
        self.plugins: dict[str, BasePlugin] = {}

    def register_builtin_plugins(self) -> None:
        # Pre-register built-in catalog plugins
        builtins = [
            {
                "id": "k8s_executor",
                "name": "K8s Executor",
                "version": "0.3.2",
                "desc": "Run TaskForge jobs as Kubernetes Jobs. Supports resource limits, namespaces, service accounts, and pod tolerations.",
                "type": "executor",
                "icon": "⚓",
                "enabled": True
            },
            {
                "id": "discord_notifier",
                "name": "Discord Notifier",
                "version": "0.2.0",
                "desc": "Send rich embed notifications to Discord channels via webhooks. Configurable color, emoji, and mention support.",
                "type": "notifier",
                "icon": "💬",
                "enabled": False
            },
            {
                "id": "git_trigger",
                "name": "Git Trigger",
                "version": "0.1.5",
                "desc": "Trigger jobs on GitHub/GitLab push, PR, tag, and release events. Validates webhook signatures automatically.",
                "type": "trigger",
                "icon": "🐙",
                "enabled": True
            },
            {
                "id": "datadog_metrics",
                "name": "Datadog Metrics",
                "version": "0.1.0",
                "desc": "Export TaskForge metrics to Datadog. Supports custom tags, service checks, and event tracking.",
                "type": "observability",
                "icon": "📊",
                "enabled": False
            }
        ]
        for b in builtins:
            self.plugins[b["id"]] = b  # type: ignore

    def get_all(self) -> list[dict[str, Any]]:
        return list(self.plugins.values())

plugin_loader = PluginLoader()
plugin_loader.register_builtin_plugins()
