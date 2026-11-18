import io
import json
from typing import Any

import pytest
from test_pipeline import FakeLLM, answer, copilot

from copilot.kb import KnowledgeBase
from copilot.pipeline import Copilot
from copilot.web import MAX_TICKET_CHARS, SESSION_SECONDS, Gate, make_app

PASSWORD = "correct-horse-battery"
NOW = 1_800_000_000.0


class Client:
    """Calls the WSGI app in-process and keeps the session cookie, like a browser."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.cookie = ""

    def post(self, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        raw = json.dumps(body or {}).encode()
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": path, "CONTENT_LENGTH": str(len(raw)),
                   "wsgi.input": io.BytesIO(raw), "HTTP_COOKIE": self.cookie}
        seen: dict[str, Any] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            seen["status"] = int(status.split()[0])
            seen["headers"] = dict(headers)

        payload = b"".join(self.app(environ, start_response))
        if set_cookie := seen["headers"].get("Set-Cookie"):
            self.cookie = set_cookie.split(";")[0]
        return seen["status"], json.loads(payload) if payload else {}


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM(answer())


@pytest.fixture
def client(kb: KnowledgeBase, llm: FakeLLM) -> Client:
    instance: Copilot = copilot(kb, llm)
    return Client(make_app(lambda: instance, PASSWORD, clock=lambda: NOW))


def test_triage_needs_a_session_and_never_calls_the_llm_without_one(
        client: Client, llm: FakeLLM) -> None:
    status, _ = client.post("/api/triage", {"text": "What is the minimum deposit?"})
    assert status == 401
    assert llm.prompts == []


def test_wrong_password_is_refused(client: Client) -> None:
    status, _ = client.post("/api/login", {"password": "guess"})
    assert status == 401
    assert client.cookie == ""


def test_signed_in_user_gets_the_triage_result(client: Client) -> None:
    assert client.post("/api/login", {"password": PASSWORD})[0] == 204
    status, result = client.post("/api/triage", {"text": "What is the minimum deposit?"})
    assert status == 200
    assert result["route"]["action"] == "assist"
    assert result["citations"][0]["section_id"] == "faq.what-is-the-minimum-deposit-amount"


def test_session_cookie_is_httponly_strict_and_secure(kb: KnowledgeBase, llm: FakeLLM) -> None:
    app = make_app(lambda: copilot(kb, llm), PASSWORD, clock=lambda: NOW)
    headers: dict[str, str] = {}
    raw = json.dumps({"password": PASSWORD}).encode()
    app({"REQUEST_METHOD": "POST", "PATH_INFO": "/api/login", "CONTENT_LENGTH": str(len(raw)),
         "wsgi.input": io.BytesIO(raw)}, lambda s, h: headers.update(h))
    assert {"HttpOnly", "SameSite=Strict", "Secure"} <= set(headers["Set-Cookie"].split("; "))


def test_oversized_and_empty_tickets_are_rejected_before_the_llm(
        client: Client, llm: FakeLLM) -> None:
    client.post("/api/login", {"password": PASSWORD})
    assert client.post("/api/triage", {"text": "x" * (MAX_TICKET_CHARS + 1)})[0] == 413
    assert client.post("/api/triage", {"text": "   "})[0] == 400
    assert llm.prompts == []


def test_no_password_configured_refuses_everything(kb: KnowledgeBase, llm: FakeLLM) -> None:
    client = Client(make_app(lambda: copilot(kb, llm), None))
    assert client.post("/api/login", {"password": ""})[0] == 503
    assert client.post("/api/triage", {"text": "hi"})[0] == 503


def test_token_expires_and_dies_with_a_password_change() -> None:
    token = Gate(PASSWORD).issue(NOW)
    assert Gate(PASSWORD).valid(token, NOW + SESSION_SECONDS - 1)
    assert not Gate(PASSWORD).valid(token, NOW + SESSION_SECONDS + 1)
    assert not Gate("new-password").valid(token, NOW)


@pytest.mark.parametrize("token", [None, "", "garbage", "99999999999.deadbeef", "abc.def"])
def test_forged_tokens_are_invalid(token: str | None) -> None:
    assert not Gate(PASSWORD).valid(token, NOW)
