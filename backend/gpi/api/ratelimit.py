"""Per-IP request limits for the public site.

The site is open to everyone, but it runs on the same small server as the nightly scraper, so one
visitor (or bot) must not be able to eat the CPU, pull the whole database in a loop or guess
passwords. The API runs as a single process, so an in-memory window per IP is enough.

The client IP comes from X-Forwarded-For set by Caddy (uvicorn runs with --proxy-headers and trusts
it because the API port is reachable only from the web container).
"""

import time
from collections import deque

from starlette.requests import Request
from starlette.responses import JSONResponse

# (path prefix, method or None for any, max requests, window seconds). The first match wins.
RULES: list[tuple[str, str | None, int, int]] = [
    ("/api/auth/login", "POST", 10, 15 * 60),
    ("/api/auth/register", "POST", 5, 60 * 60),
    ("/api/games/export.csv", None, 10, 10 * 60),
    ("/api/", None, 240, 60),
]

_hits: dict[tuple[str, str], deque] = {}
_last_sweep = 0.0


def _rule(path: str, method: str):
    for prefix, m, limit, window in RULES:
        if path.startswith(prefix) and (m is None or m == method):
            return prefix, limit, window
    return None


def _sweep(now: float):
    """Drop IPs that have been quiet for an hour so the table does not grow forever."""
    global _last_sweep
    if now - _last_sweep < 300:
        return
    _last_sweep = now
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > 3600]:
        del _hits[key]


def check(ip: str, path: str, method: str, now: float | None = None) -> int | None:
    """Record a request; return seconds to wait if the IP is over its limit, else None."""
    rule = _rule(path, method)
    if not rule:
        return None
    prefix, limit, window = rule
    now = time.monotonic() if now is None else now
    _sweep(now)
    q = _hits.setdefault((ip, prefix), deque())
    while q and now - q[0] >= window:
        q.popleft()
    if len(q) >= limit:
        return int(window - (now - q[0])) + 1
    q.append(now)
    return None


async def middleware(request: Request, call_next):
    ip = request.client.host if request.client else "?"
    wait = check(ip, request.url.path, request.method)
    if wait is not None:
        return JSONResponse({"detail": "rate_limited"}, status_code=429, headers={"Retry-After": str(wait)})
    return await call_next(request)
