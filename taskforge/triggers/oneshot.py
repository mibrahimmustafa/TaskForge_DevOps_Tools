from datetime import datetime
from apscheduler.triggers.date import DateTrigger as ApDateTrigger
from taskforge.triggers.base import BaseTrigger

class OneShotTrigger(BaseTrigger):
    def __init__(self, run_at: datetime | None = None) -> None:
        self.run_at = run_at or datetime.now()

    def to_apscheduler_trigger(self) -> ApDateTrigger:
        return ApDateTrigger(run_date=self.run_at)
