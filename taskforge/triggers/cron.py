from apscheduler.triggers.cron import CronTrigger as ApCronTrigger

from taskforge.triggers.base import BaseTrigger


class CronTrigger(BaseTrigger):
    def __init__(self, expr: str, timezone: str = "UTC") -> None:
        self.expr = expr
        self.timezone = timezone

    def to_apscheduler_trigger(self) -> ApCronTrigger:
        return ApCronTrigger.from_crontab(self.expr, timezone=self.timezone)
