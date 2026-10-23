import re
from apscheduler.triggers.interval import IntervalTrigger as ApIntervalTrigger
from taskforge.triggers.base import BaseTrigger

class IntervalTrigger(BaseTrigger):
    def __init__(self, expr: str) -> None:
        self.expr = expr

    def to_apscheduler_trigger(self) -> ApIntervalTrigger:
        clean = self.expr.lower().replace("every", "").strip()
        seconds = 60
        m = re.match(r"^(\d+)\s*([smhd])?$", clean)
        if m:
            val = int(m.group(1))
            unit = m.group(2) or "s"
            if unit == "s":
                seconds = val
            elif unit == "m":
                seconds = val * 60
            elif unit == "h":
                seconds = val * 3600
            elif unit == "d":
                seconds = val * 86400
        elif clean.isdigit():
            seconds = int(clean)

        return ApIntervalTrigger(seconds=seconds)
