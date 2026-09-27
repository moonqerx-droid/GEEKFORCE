import pytest
from pydantic import ValidationError

from app.schemas.incident import IncidentBroadcastCreate, IncidentStatus


def test_broadcast_contract_trims_message():
    payload = IncidentBroadcastCreate(
        message="  CRM недоступна, команда работает над восстановлением.  ",
        request_key="demo-update-1",
        expected_revision=2,
    )

    assert payload.message == "CRM недоступна, команда работает над восстановлением."
    assert payload.request_key == "demo-update-1"
    assert payload.expected_revision == 2


@pytest.mark.parametrize(
    "values",
    [
        {"message": "   ", "request_key": "x", "expected_revision": 1},
        {"message": "Обновление", "request_key": "bad key", "expected_revision": 1},
        {"message": "Обновление", "request_key": "x", "expected_revision": 0},
    ],
)
def test_broadcast_contract_rejects_invalid_input(values):
    with pytest.raises(ValidationError):
        IncidentBroadcastCreate(**values)


def test_incident_status_values_are_stable():
    assert [status.value for status in IncidentStatus] == ["CANDIDATE", "ACTIVE", "RESOLVED"]
