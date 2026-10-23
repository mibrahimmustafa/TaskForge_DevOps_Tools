from datetime import datetime

import pytest
from pydantic import ValidationError

from taskforge.jobs.models import Job, Pipeline
from taskforge.triggers import get_trigger


@pytest.mark.parametrize("expression", ["nope", "0s", "-1m", "every 0h", "3 weeks"])
def test_invalid_intervals_rejected(expression):
    with pytest.raises(ValueError):
        get_trigger("interval", expression).to_apscheduler_trigger()


def test_oneshot_preserves_offset_and_event_is_rejected():
    requested = "2099-10-23T12:00:00+03:00"
    result = get_trigger("oneshot", requested).to_apscheduler_trigger().run_date
    assert result == datetime.fromisoformat(requested)
    with pytest.raises(ValueError):
        get_trigger("oneshot", "2099-10-23T12:00:00")
    with pytest.raises(ValueError):
        get_trigger("event", "job.success")


@pytest.mark.parametrize(
    "changes",
    [{"timeout_seconds": 0}, {"max_retries": -1}, {"id": "bad'id"}, {"retry_delay_seconds": 0}],
)
def test_job_bounds(changes):
    with pytest.raises(ValidationError):
        Job.model_validate({"id": "ok", "name": "Example", **changes})


@pytest.mark.parametrize("needs", [["missing"], ["test"]])
def test_invalid_pipeline_graph(needs):
    with pytest.raises(ValidationError):
        Pipeline(
            id="ci",
            name="CI",
            steps=[
                {
                    "id": "test",
                    "needs": needs,
                    "job": {"id": "test", "name": "Test", "trigger": "manual"},
                }
            ],
        )
