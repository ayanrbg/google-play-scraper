"""Shared HTTP plumbing: rate-limited routes (the server's own IP + optional proxies) and retries.

Google throttles by IP, so every route has its own pace. Heavy requests (chart RPC, ~1.2 MB
uncompressed) always go direct to spare proxy bandwidth; light ones (app pages, suggest,
developer/similar pages) are spread over whichever route frees up first. A proxy that keeps
failing or gets throttled is benched for a while and the others carry on.
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests

from gpi.settings import get_settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
BENCH_AFTER_FAILS = 3
BENCH_SECONDS = 15 * 60

log = logging.getLogger("gpi")


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.penalty_until = 0.0

    def ready_at(self) -> float:
        return max(self.next_at, self.penalty_until)

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_at, self.penalty_until)
            self.next_at = start + self.interval * random.uniform(0.8, 1.2)
        delay = start - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def back_off(self, seconds: float):
        with self.lock:
            self.penalty_until = max(self.penalty_until, time.monotonic() + seconds)


@dataclass
class Route:
    name: str
    limiter: RateLimiter
    proxies: dict | None = None
    fails: int = 0
    bench_until: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def ok(self):
        self.fails = 0

    def failed(self, reason: str):
        with self.lock:
            self.fails += 1
            if self.proxies and self.fails >= BENCH_AFTER_FAILS and self.bench_until < time.monotonic():
                self.bench_until = time.monotonic() + BENCH_SECONDS
                log.warning("прокси %s выключен на %d мин: %s", self.name, BENCH_SECONDS // 60, reason)


# ----------------------------- throttling stats -----------------------------

_stats_lock = threading.Lock()
_throttled = 0
_last_warned = 0.0


def note_throttled(route: Route, status: str, pause: float):
    global _throttled, _last_warned
    with _stats_lock:
        _throttled += 1
        now = time.monotonic()
        # One journal line per minute is enough to see that Google is pushing back.
        if now - _last_warned > 60:
            _last_warned = now
            log.warning("Google ограничивает запросы (HTTP %s, канал %s), пауза %d с; всего ограничений за прогон: %d",
                        status, route.name, pause, _throttled)


def throttle_count() -> int:
    return _throttled


def reset_throttle_count():
    global _throttled
    with _stats_lock:
        _throttled = 0


# ----------------------------- routes -----------------------------

_routes: list[Route] | None = None
_routes_lock = threading.Lock()
_local = threading.local()


def parse_proxy(spec: str) -> str | None:
    """Accept `http://user:pass@host:port` or Webshare-style `host:port:user:pass`."""
    spec = spec.strip()
    if not spec:
        return None
    if "://" in spec:
        return spec
    parts = spec.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    if len(parts) == 2:
        return f"http://{spec}"
    return None


def build_routes(direct_rps: float, proxy_specs: list[str], proxy_rps: float) -> list[Route]:
    routes = [Route(name="сервер", limiter=RateLimiter(direct_rps))]
    for spec in proxy_specs:
        url = parse_proxy(spec)
        if url:
            host = urlsplit(url).hostname or "?"
            routes.append(Route(name=host, limiter=RateLimiter(proxy_rps), proxies={"http": url, "https": url}))
    return routes


def routes() -> list[Route]:
    global _routes
    with _routes_lock:
        if _routes is None:
            cfg = get_settings()
            specs = [s for s in cfg.proxies.replace("\n", ",").split(",") if s.strip()]
            _routes = build_routes(cfg.requests_per_second, specs, cfg.proxy_rps)
            if len(_routes) > 1:
                log.info("сеть: сервер %.1f запр/с + %d прокси по %.1f запр/с (чарты %s)",
                         cfg.requests_per_second, len(_routes) - 1, cfg.proxy_rps,
                         "тоже через прокси" if cfg.proxy_heavy else "напрямую")
        return _routes


def pick(heavy: bool = False) -> Route:
    """The route that can send soonest (heavy requests: the server's own IP unless proxy_heavy)."""
    rs = routes()
    if len(rs) == 1 or (heavy and not get_settings().proxy_heavy):
        return rs[0]
    now = time.monotonic()
    healthy = [r for r in rs if r.bench_until <= now] or rs[:1]
    return min(healthy, key=lambda r: r.limiter.ready_at())


def throttle():
    """For callers that do their own HTTP (google-play-scraper): pace the direct route."""
    routes()[0].limiter.wait()


def session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        # Pre-accept Google's cookie consent so servers in the EU get content, not the consent page.
        s.cookies.set("CONSENT", "YES+", domain=".google.com")
        s.cookies.set("SOCS", "CAI", domain=".google.com")
        _local.session = s
    return s


class NotFound(Exception):
    pass


def request(method: str, url: str, retries: int = 4, heavy: bool = False, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", get_settings().http_timeout)
    last: Exception | None = None
    for attempt in range(retries):
        route = pick(heavy)
        route.limiter.wait()
        try:
            resp = session().request(method, url, proxies=route.proxies, **kwargs)
        except requests.RequestException as e:
            last = e
            route.failed(type(e).__name__)
            # A dead proxy is not a reason to wait; the next attempt picks another route.
            if not route.proxies:
                time.sleep(2 ** attempt + random.random())
            continue
        if resp.status_code == 404:
            route.ok()
            raise NotFound(url)
        if resp.status_code in (429, 503):
            pause = 30 * (attempt + 1)
            route.limiter.back_off(pause)
            route.failed(f"HTTP {resp.status_code}")
            note_throttled(route, str(resp.status_code), pause)
            last = RuntimeError(f"HTTP {resp.status_code}")
            continue
        if resp.status_code == 407:
            route.failed("прокси отклонил логин (HTTP 407)")
            last = RuntimeError("HTTP 407")
            continue
        if resp.status_code >= 500:
            last = RuntimeError(f"HTTP {resp.status_code}")
            time.sleep(2 ** attempt + random.random())
            continue
        resp.raise_for_status()
        route.ok()
        return resp
    raise last or RuntimeError("request failed")
