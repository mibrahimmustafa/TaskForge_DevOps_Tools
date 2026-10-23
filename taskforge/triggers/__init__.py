from taskforge.triggers.base import BaseTrigger
from taskforge.triggers.cron import CronTrigger
from taskforge.triggers.interval import IntervalTrigger
from taskforge.triggers.webhook import WebhookTrigger
from taskforge.triggers.oneshot import OneShotTrigger
from taskforge.jobs.models import TriggerType

def get_trigger(trigger_type: TriggerType, expr: str) -> BaseTrigger:
    if trigger_type == TriggerType.CRON:
        return CronTrigger(expr)
    elif trigger_type == TriggerType.INTERVAL:
        return IntervalTrigger(expr)
    elif trigger_type == TriggerType.WEBHOOK:
        return WebhookTrigger(expr)
    elif trigger_type == TriggerType.ONESHOT:
        return OneShotTrigger()
    return CronTrigger(expr)

__all__ = [
    "BaseTrigger",
    "CronTrigger",
    "IntervalTrigger",
    "WebhookTrigger",
    "OneShotTrigger",
    "get_trigger",
]
