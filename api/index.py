"""Vercel entry point: the WSGI app from `copilot.web`, built from the source tree.

The source tree goes first on the path, so `copilot` resolves next to its prompts and KB snapshot
(bundled through `includeFiles` in vercel.json). Vercel hands a rewritten request to this function
with PATH_INFO `/api/index`; vercel.json passes the original route in `?route=`, restored here.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copilot.web import app_from_env  # noqa: E402

_app = app_from_env()


def app(environ, start_response):  # type: ignore[no-untyped-def]
    """Restore the original `/api/<route>` path, then hand over to the co-pilot app."""
    route = parse_qs(environ.get("QUERY_STRING", "")).get("route", [""])[0]
    if route:
        environ = {**environ, "PATH_INFO": f"/api/{route}"}
    return _app(environ, start_response)
