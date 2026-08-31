"""The acknowledgement contract.

A real incident: the collector serialised absent optional fields as null, the
schema declared `detail` non-nullable, and every ack came back 422. Because an
unacknowledged command stays pending, the collector re-ran it on every poll --
so one request from a caregiver buzzed the subject's phone every ten seconds.

The lesson is not "validate harder". A rejected acknowledgement had a
consequence far worse than a rejected request, and nothing in the type system
said so. These tests pin the shapes a client may legitimately send.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.commands import CheckinPartialIn, CommandAckIn, CommandResponseIn


def test_ack_accepts_an_explicit_null_detail() -> None:
    """kotlinx.serialization emits null for an absent optional by default."""
    ack = CommandAckIn.model_validate({"status": "executed", "detail": None})
    assert ack.detail is None


def test_ack_accepts_an_omitted_detail() -> None:
    assert CommandAckIn.model_validate({"status": "executed"}).detail is None


def test_ack_accepts_a_populated_detail() -> None:
    ack = CommandAckIn.model_validate({"status": "failed", "detail": {"reason": "timeout"}})
    assert ack.detail == {"reason": "timeout"}


def test_ack_accepts_a_null_executed_at() -> None:
    assert CommandAckIn.model_validate({"status": "sent", "executed_at": None}).executed_at is None


@pytest.mark.parametrize("status", ["sent", "delivered", "executed", "failed", "cancelled"])
def test_every_status_the_collector_may_report_is_accepted(status: str) -> None:
    assert CommandAckIn.model_validate({"status": status}).status.value == status


def test_an_invented_status_is_still_rejected() -> None:
    """Tolerant about shape, strict about meaning."""
    with pytest.raises(ValidationError):
        CommandAckIn.model_validate({"status": "probably-fine"})


def test_response_accepts_the_collector_payload() -> None:
    payload = {
        "response": "im_ok",
        "responded_at": "2026-08-31T17:28:22+02:00",
        "source": "phone",
    }
    assert CommandResponseIn.model_validate(payload).response.value == "im_ok"


def test_checkin_report_accepts_an_empty_result() -> None:
    assert CheckinPartialIn.model_validate({"partial": True, "result": {}}).result == {}


def test_checkin_report_accepts_the_two_stage_shapes() -> None:
    first = CheckinPartialIn.model_validate(
        {"partial": True, "result": {"battery_pct": 100, "watch_bt_connected": True}}
    )
    second = CheckinPartialIn.model_validate(
        {"partial": False, "result": {"battery_pct": 100, "bpm": 72}}
    )
    assert first.partial is True
    assert second.result["bpm"] == 72
