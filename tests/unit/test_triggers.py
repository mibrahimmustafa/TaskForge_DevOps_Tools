from apscheduler.triggers.cron import CronTrigger as ApCronTrigger
from apscheduler.triggers.date import DateTrigger as ApDateTrigger
from apscheduler.triggers.interval import IntervalTrigger as ApIntervalTrigger

from taskforge.jobs.models import TriggerType
from taskforge.triggers import (
    CronTrigger,
    IntervalTrigger,
    OneShotTrigger,
    WebhookTrigger,
    get_trigger,
)


def test_cron_trigger_crontab():
    trigger = CronTrigger("0 2 * * *")
    aps = trigger.to_apscheduler_trigger()
    assert isinstance(aps, ApCronTrigger)

    step_trigger = CronTrigger("*/15 * * * *")
    aps_step = step_trigger.to_apscheduler_trigger()
    assert isinstance(aps_step, ApCronTrigger)


def test_interval_trigger_parsing():
    cases = [
        ("every 30s", 30),
        ("every 5m", 300),
        ("every 2h", 7200),
        ("every 1d", 86400),
        ("120", 120),
    ]
    for expr, expected_seconds in cases:
        trigger = IntervalTrigger(expr)
        aps = trigger.to_apscheduler_trigger()
        assert isinstance(aps, ApIntervalTrigger)
        assert aps.interval.total_seconds() == expected_seconds


def test_webhook_trigger_no_apscheduler():
    trigger = WebhookTrigger("secret-key")
    assert trigger.to_apscheduler_trigger() is None


def test_oneshot_trigger_apscheduler():
    trigger = OneShotTrigger()
    aps = trigger.to_apscheduler_trigger()
    assert isinstance(aps, ApDateTrigger)


def test_get_trigger_factory():
    cron = get_trigger(TriggerType.CRON, "0 0 * * *")
    assert isinstance(cron, CronTrigger)

    interval = get_trigger(TriggerType.INTERVAL, "every 10m")
    assert isinstance(interval, IntervalTrigger)

    webhook = get_trigger(TriggerType.WEBHOOK, "token-123")
    assert isinstance(webhook, WebhookTrigger)

    oneshot = get_trigger(TriggerType.ONESHOT, "2026-10-23T12:00:00+00:00")
    assert isinstance(oneshot, OneShotTrigger)
