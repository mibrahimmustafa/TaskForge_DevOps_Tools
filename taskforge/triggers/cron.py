from apscheduler.triggers.cron import CronTrigger as ApCronTrigger
from taskforge.triggers.base import BaseTrigger

class CronTrigger(BaseTrigger):
    def __init__(self, expr: str) -> None:
        self.expr = expr

    def to_apscheduler_trigger(self) -> ApCronTrigger:
        # expr standard is: min hour day month day_of_week
        # e.g., "0 2 * * *" or "*/5 * * * *"
        return ApCronTrigger.from_crontab(self.expr)
