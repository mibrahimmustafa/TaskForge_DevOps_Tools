import re

from apscheduler.triggers.interval import IntervalTrigger as ApIntervalTrigger

from taskforge.triggers.base import BaseTrigger


class IntervalTrigger(BaseTrigger):
    def __init__(self, expr: str) -> None:
        self.expr = expr

    def to_apscheduler_trigger(self) -> ApIntervalTrigger:
        match = re.fullmatch(r"(?:every\s+)?([1-9]\d*)\s*([smhd])?", self.expr.strip().lower())
        if not match:
            raise ValueError("Use a positive interval such as 'every 5m'")
        seconds = int(match[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match[2] or "s"]
        return ApIntervalTrigger(seconds=seconds, timezone="UTC")
