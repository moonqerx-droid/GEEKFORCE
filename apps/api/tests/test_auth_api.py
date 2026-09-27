from app.core.security import hash_password, utc_now
from app.models.auth import User


def verified_user(db_session, *, role="employee"):
    user = User(first_name="Анна", last_name="Иванова", email=f"{role}@example.ru",
                department="it", password_hash=hash_password("StrongPass7"), role=role,
                email_verified_at=utc_now())
    db_session.add(user)
    db_session.commit()
    return user


def test_login_sets_hardened_cookie_and_me_returns_identity(client, db_session):
    user = verified_user(db_session)
    response = client.post("/api/auth/login", json={
        "email": user.email, "password": "StrongPass7", "remember_me": False,
    })

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert client.get("/api/auth/me").json()["role"] == "employee"


def test_logout_revokes_cookie(client, db_session):
    user = verified_user(db_session)
    client.post("/api/auth/login", json={"email": user.email, "password": "StrongPass7"})
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_forgot_password_is_neutral_for_unknown_email(client):
    response = client.post("/api/auth/forgot-password", json={"email": "missing@example.ru"})
    assert response.status_code == 202
    assert response.json()["code"] == "password_reset_requested"


def test_verify_email_accepts_email_and_six_digit_code(client):
    response = client.post("/api/auth/verify-email", json={
        "email": "employee@example.ru", "code": "123456",
    })
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_or_expired_code"


def test_auth_mutation_rejects_untrusted_origin(client):
    response = client.post(
        "/api/auth/forgot-password",
        json={"email": "origin@example.ru"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_login_is_rate_limited(client):
    payload = {"email": "rate-limit@example.ru", "password": "WrongPassword7"}
    for _ in range(5):
        assert client.post("/api/auth/login", json=payload).status_code == 401
    assert client.post("/api/auth/login", json=payload).status_code == 429
