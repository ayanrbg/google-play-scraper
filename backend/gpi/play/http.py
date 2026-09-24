"""Shared HTTP plumbing: a process-wide rate limiter and retrying requests session.

Google throttles by IP. Every call to Google Play (ours or google-play-scraper's)
goes through `throttle()` so the whole process stays under the configured pace.
"""

import random
import threading
import time

import requests

from gpi.settings import get_settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.penalty_until = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_at, self.penalty_until)
            self.next_at = start + self.interval * random.uniform(0.8, 1.2)
        delay = start - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def back_off(self, seconds: float):
        """Called on 429/503: pause everyone, not just the failing thread."""
        with self.lock:
            self.penalty_until = max(self.penalty_until, time.monotonic() + seconds)


_limiter: RateLimiter | None = None
_local = threading.local()


def limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(get_settings().requests_per_second)
    return _limiter


def throttle():
    limiter().wait()


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


def request(method: str, url: str, retries: int = 4, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", get_settings().http_timeout)
    last: Exception | None = None
    for attempt in range(retries):
        throttle()
        try:
            resp = session().request(method, url, **kwargs)
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** attempt + random.random())
            continue
        if resp.status_code == 404:
            raise NotFound(url)
        if resp.status_code in (429, 503):
            limiter().back_off(30 * (attempt + 1))
            last = RuntimeError(f"HTTP {resp.status_code}")
            continue
        if resp.status_code >= 500:
            last = RuntimeError(f"HTTP {resp.status_code}")
            time.sleep(2 ** attempt + random.random())
            continue
        resp.raise_for_status()
        return resp
    raise last or RuntimeError("request failed")
