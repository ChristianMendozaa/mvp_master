from uuid import uuid4

import pytest
from mvp_common.contracts import EventEnvelope, SecretReference
from mvp_common.logging import redact
from pydantic import ValidationError


def test_secret_reference_rejects_value_like_content() -> None:
    with pytest.raises(ValidationError):
        SecretReference(store="local", namespace="agents", key="API_KEY=value")


def test_event_envelope_is_strict() -> None:
    event = EventEnvelope(
        id=uuid4(),
        source="control-plane",
        type="com.mvp.work_item.ready.v1",
        subject="work-item/123",
        organization_id=uuid4(),
        aggregate_version=1,
        correlation_id=uuid4(),
        data={"work_item_id": "123"},
    )
    assert event.specversion == "1.0"


def test_nested_values_are_redacted() -> None:
    assert redact({"nested": {"access_token": "unsafe"}, "safe": "ok"}) == {
        "nested": {"access_token": "[REDACTED]"},
        "safe": "ok",
    }
