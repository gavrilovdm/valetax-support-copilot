"""HTTP layer for the demo page: a password gate and the triage endpoint.

Plain WSGI, no framework: Vercel's Python runtime serves `app` from `api/index.py`, and
`uv run copilot serve` serves the same app locally.

Access control. The page is public, the LLM behind it is not free, so every LLM call needs a
session. The password lives only in the server's environment (`COPILOT_WEB_PASSWORD`: an encrypted
Vercel environment variable in production, `.env` locally) and never reaches the browser bundle.
A correct password gets an HttpOnly cookie holding an expiry signed with HMAC-SHA256 keyed by the
password, so changing the password logs every session out. No password configured → every request
is refused (fail closed). The proxy key stays server-side as well; the browser only ever talks to
this app.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from http.cookies import SimpleCookie
from typing import Any

from pydantic import BaseModel, ValidationError

from copilot.llm import LLMError
from copilot.pipeline import Copilot, Ticket

COOKIE = "copilot_session"
SESSION_SECONDS = 12 * 3600
MAX_TICKET_CHARS = 4000
MAX_BODY_BYTES = 16_384

StartResponse = Callable[[str, list[tuple[str, str]]], Any]
WSGIApp = Callable[[dict[str, Any], StartResponse], Iterable[bytes]]

_STATUS = {200: "200 OK", 204: "204 No Content", 400: "400 Bad Request",
           401: "401 Unauthorized", 404: "404 Not Found", 405: "405 Method Not Allowed",
           413: "413 Content Too Large", 503: "503 Service Unavailable"}


@dataclass(frozen=True)
class Gate:
    """Checks the password and issues and verifies signed session tokens."""

    password: str

    def check(self, candidate: str) -> bool:
        """Constant-time comparison, so the response time does not leak the password."""
        return hmac.compare_digest(candidate.encode(), self.password.encode())

    def issue(self, now: float) -> str:
        """A token `<expiry>.<signature>` valid for SESSION_SECONDS."""
        expiry = str(int(now) + SESSION_SECONDS)
        return f"{expiry}.{self._sign(expiry)}"

    def valid(self, token: str | None, now: float) -> bool:
        """True for an unexpired token signed with the current password."""
        if not token or "." not in token:
            return False
        expiry, signature = token.split(".", 1)
        if not expiry.isdigit() or int(expiry) < now:
            return False
        return hmac.compare_digest(signature, self._sign(expiry))

    def _sign(self, message: str) -> str:
        return hmac.new(self.password.encode(), message.encode(), hashlib.sha256).hexdigest()


class _TriageRequest(BaseModel):
    text: str


class _LoginRequest(BaseModel):
    password: str


@dataclass(frozen=True)
class _Response:
    status: int
    body: dict[str, Any] | None = None
    cookie: str | None = None


def make_app(copilot: Callable[[], Copilot], password: str | None,
             clock: Callable[[], float] = time.time, secure_cookie: bool = True) -> WSGIApp:
    """Build the WSGI app. `copilot` is called lazily, once per request that passed the gate."""
    gate = Gate(password) if password else None

    def cookie(token: str, max_age: int) -> str:
        parts = [f"{COOKIE}={token}", "Path=/", "HttpOnly", "SameSite=Strict",
                 f"Max-Age={max_age}"]
        return "; ".join([*parts, "Secure"] if secure_cookie else parts)

    def route(method: str, path: str, body: bytes, session: str | None) -> _Response:
        if gate is None:
            return _Response(503, {"error": "COPILOT_WEB_PASSWORD is not set on the server"})
        if path == "/api/login":
            if method != "POST":
                return _Response(405, {"error": "POST only"})
            login = _parse(_LoginRequest, body)
            if login is None or not gate.check(login.password):
                return _Response(401, {"error": "wrong password"})
            return _Response(204, cookie=cookie(gate.issue(clock()), SESSION_SECONDS))
        if path == "/api/logout":
            return _Response(204, cookie=cookie("", 0))
        if not gate.valid(session, clock()):
            return _Response(401, {"error": "sign in first"})
        if path == "/api/session":
            return _Response(200, {"ok": True})
        if path == "/api/triage":
            if method != "POST":
                return _Response(405, {"error": "POST only"})
            request = _parse(_TriageRequest, body)
            text = request.text.strip() if request else ""
            if not text:
                return _Response(400, {"error": "the ticket text is empty"})
            if len(text) > MAX_TICKET_CHARS:
                return _Response(413, {"error": f"tickets are capped at {MAX_TICKET_CHARS} chars"})
            try:
                result = copilot().triage(Ticket(id=f"web-{uuid.uuid4().hex[:8]}", text=text))
            except LLMError as exc:
                return _Response(503, {"error": f"configuration error: {exc}"})
            return _Response(200, result.model_dump(mode="json"))
        return _Response(404, {"error": "not found"})

    def app(environ: dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length > MAX_BODY_BYTES:
            response = _Response(413, {"error": "request too large"})
        else:
            body = environ["wsgi.input"].read(length) if length else b""
            response = route(environ.get("REQUEST_METHOD", "GET"),
                             environ.get("PATH_INFO", "/"), body,
                             _session(environ.get("HTTP_COOKIE", "")))
        payload = json.dumps(response.body, ensure_ascii=False).encode() if response.body else b""
        headers = [("Content-Type", "application/json; charset=utf-8"),
                   ("Cache-Control", "no-store")]
        if response.cookie:
            headers.append(("Set-Cookie", response.cookie))
        start_response(_STATUS[response.status], headers)
        return [payload]

    return app


def _parse[T: BaseModel](model: type[T], body: bytes) -> T | None:
    try:
        return model.model_validate_json(body or b"{}")
    except ValidationError:
        return None


def _session(header: str) -> str | None:
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(header)
    except Exception:  # a malformed Cookie header is the client's problem, not a 500
        return None
    morsel = jar.get(COOKIE)
    return morsel.value if morsel else None


def app_from_env(secure_cookie: bool = True) -> WSGIApp:
    """The app wired from the environment, with one co-pilot per process."""
    from copilot.config import Settings

    Settings.from_env()  # loads .env locally, so the password below is found there too
    return make_app(cache(Copilot.from_env), os.environ.get("COPILOT_WEB_PASSWORD"),
                    secure_cookie=secure_cookie)
