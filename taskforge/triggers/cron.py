from apscheduler.triggers.cron import CronTrigger as ApCronTrigger

from taskforge.triggers.base import BaseTrigger
from taskforge.triggers.h_cron import expand_jenkins_cron


class CronTrigger(BaseTrigger):
    def __init__(self, expr: str, timezone: str = "UTC", seed: str = "") -> None:
        self.raw_expr = expr
        self.seed = seed or "taskforge"
        self.expr = expand_jenkins_cron(expr, self.seed)
        self.timezone = timezone

    def to_apscheduler_trigger(self) -> ApCronTrigger:
        return ApCronTrigger.from_crontab(self.expr, timezone=self.timezone)
