import pytest
from pydantic import ValidationError

from app.schemas.auth import EmployeeRegister


def registration(**changes):
    data = {
        "first_name": "Анна",
        "last_name": "Иванова",
        "email": " A@EXAMPLE.RU ",
        "department": "it",
        "password": "StrongPass7",
        "password_confirmation": "StrongPass7",
        "accepted_terms": True,
    }
    data.update(changes)
    return EmployeeRegister(**data)


@pytest.mark.parametrize("name", ["Анна-Мария", "O'Connor", "Ли"])
def test_registration_accepts_supported_names(name):
    payload = registration(first_name=name)
    assert payload.first_name == name
    assert payload.email == "a@example.ru"


@pytest.mark.parametrize("name", ["A1", "A\nB", "-"])
def test_registration_rejects_invalid_names(name):
    with pytest.raises(ValidationError):
        registration(first_name=name)


@pytest.mark.parametrize(
    "password",
    ["short7A", "alllowercase7", "ALLUPPERCASE7", "NoDigitsHere", "Has Space7A"],
)
def test_registration_rejects_weak_password(password):
    with pytest.raises(ValidationError):
        registration(password=password, password_confirmation=password)


def test_registration_rejects_mismatch_and_terms():
    with pytest.raises(ValidationError):
        registration(password_confirmation="OtherPass7")
    with pytest.raises(ValidationError):
        registration(accepted_terms=False)
