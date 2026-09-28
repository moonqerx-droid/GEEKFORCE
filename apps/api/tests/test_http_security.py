import re

import pytest
from fastapi.routing import APIRoute

from app.main import app


STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
UNTRUSTED_ORIGIN = {"Origin": "https://evil.example"}
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "content-security-policy": (
        "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ),
}


def state_changing_api_routes():
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        for method in sorted(route.methods & STATE_CHANGING_METHODS):
            path = re.sub(r"{[^}]+}", "test-id", route.path)
            yield pytest.param(method, path, id=f"{method}-{route.path}")


@pytest.mark.parametrize(("method", "path"), state_changing_api_routes())
def test_every_state_changing_api_route_rejects_an_untrusted_origin(client, method, path):
    response = client.request(method, path, headers=UNTRUSTED_ORIGIN)

    assert response.status_code == 403
    assert response.json() == {"detail": "Untrusted origin"}


@pytest.mark.parametrize("method", sorted(STATE_CHANGING_METHODS))
def test_trusted_origin_check_covers_every_state_changing_method(client, method):
    response = client.request(method, "/api/conversations", headers=UNTRUSTED_ORIGIN)

    assert response.status_code == 403
    assert response.json() == {"detail": "Untrusted origin"}


@pytest.mark.parametrize(
    ("method", "path", "headers"),
    [
        pytest.param("GET", "/health", {}, id="success"),
        pytest.param("GET", "/api/missing", {}, id="not-found"),
        pytest.param("POST", "/api/conversations", UNTRUSTED_ORIGIN, id="origin-rejection"),
    ],
)
def test_api_responses_include_security_headers(client, method, path, headers):
    response = client.request(method, path, headers=headers)

    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
