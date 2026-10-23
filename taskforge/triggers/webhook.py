from taskforge.triggers.base import BaseTrigger

class WebhookTrigger(BaseTrigger):
    def __init__(self, expr: str = "on POST") -> None:
        self.expr = expr

    def to_apscheduler_trigger(self):
        # Webhook jobs are not on a time schedule in APScheduler, they are triggered by HTTP requests
        return None
