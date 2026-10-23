from datetime import datetime
from zoneinfo import ZoneInfo

from taskforge.jobs.models import TriggerType
from taskforge.triggers.base import BaseTrigger
from taskforge.triggers.cron import CronTrigger
from taskforge.triggers.interval import IntervalTrigger
from taskforge.triggers.oneshot import OneShotTrigger
from taskforge.triggers.webhook import WebhookTrigger


def get_trigger(trigger_type: TriggerType, expr: str, timezone: str = "UTC") -> BaseTrigger:
    ZoneInfo(timezone)
    if trigger_type == TriggerType.CRON:
        return CronTrigger(expr, timezone)
    if trigger_type == TriggerType.INTERVAL:
        return IntervalTrigger(expr)
    if trigger_type in (TriggerType.WEBHOOK, TriggerType.MANUAL):
        return WebhookTrigger(expr)
    if trigger_type == TriggerType.ONESHOT:
        date = datetime.fromisoformat(expr.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("One-shot dates must include a UTC offset")
        return OneShotTrigger(date)
    raise ValueError(f"Unsupported trigger: {trigger_type}")


__all__ = [
    "BaseTrigger",
    "CronTrigger",
    "IntervalTrigger",
    "OneShotTrigger",
    "WebhookTrigger",
    "get_trigger",
]
