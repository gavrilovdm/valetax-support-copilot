# ADR-023: Web demo on Vercel, behind a password, through the local proxy

Status: accepted · 2026-11-19

## Context

Reviewers want to try the co-pilot without installing anything. In development the LLM is reached
through llm-proxy on the author's machine; a public page that calls it can be abused to burn the
author's LLM quota.

## Options

- CLI only (D14): no abuse surface, but nobody tries it.
- A Streamlit/FastAPI app on a server: a second runtime and dependencies for a demo.
- A static page plus one Python function on Vercel that runs the same `Copilot`, reaching
  llm-proxy through its ngrok tunnel (as gavrisalive does).

## Decision

Third option. `copilot.web` is plain WSGI (no framework, no new dependency); Vercel serves it from
`api/index.py`, `uv run copilot serve` serves the same app locally. Access:

- One password, stored only as an encrypted Vercel environment variable (`COPILOT_WEB_PASSWORD`)
  and in the local `.env`; never in the page or the repo. Generated with 144 bits of entropy,
  so guessing it online is not a practical attack and a login rate limit is not needed.
- A correct password sets an HttpOnly, Secure, SameSite=Strict cookie holding an expiry signed with
  HMAC-SHA256 keyed by the password; sessions last 12 h. Changing the password ends all sessions.
- No password configured → every request is refused.
- The proxy key and the ngrok URL stay server-side; the model is fixed on the server (Sonnet), the
  ticket is capped at 4,000 characters, the request body at 16 KB.
- Kill switch: stop ngrok (or llm-proxy) and the page can no longer reach an LLM.

## Consequences

- Anyone holding the password can spend tokens until it is rotated. There is no per-user or daily
  cap: serverless instances share no memory, and a cap needs shared storage (Upstash Redis, as in
  gavrisalive). Worth adding before the link goes beyond a few reviewers.
- The demo works only while the author's machine, llm-proxy and the ngrok tunnel are up.
- The demo writes no audit log: a Vercel function has no persistent disk. Fine for a demo with
  synthetic tickets; in production the audit record goes to a database (PHASE2.md §3).
- Unknown paths reach the function and get 401 without a session; only `public/` is static, and
  `.vercelignore` uploads nothing but the code, prompts and KB snapshot (no `.env`, eval data or
  reports).

## Evidence

tests/test_web.py (gate, cookie flags, token expiry and forgery, input caps, fail closed).
