"""In-memory rate limiting for the Course Planner FastAPI app.

Why this exists
---------------
``/api/plan`` and ``/api/four-year-plan`` invoke Gemini per request and
``/api/workday/sync`` spins up a Playwright browser. Without limits, a single
user (or attacker) can spam regenerate and burn the API budget ("denial of
wallet") while also collapsing UX for everyone else.

This module provides a *zero-dependency* token-bucket limiter with three
independent scopes per route:

1. **Per-IP rate**            — protects against anonymous flooding.
2. **Per-user rate**          — protects against an authenticated user spamming.
3. **Per-user concurrency**   — caps simultaneous in-flight expensive jobs.

Each scope is checked independently. The first scope to deny wins, and the
response carries a structured JSON body identifying which scope rejected it so
the frontend can show an accurate message and never confuse this with the
existing "please upload your transcript" 400 error.

Usage
-----
The limiter is exposed as a *FastAPI dependency factory*. Each route that needs
limiting calls ``limit("plan")`` (etc.) once at module load time, which returns
a dependency callable. The dependency:

* reads the client IP from ``request.client.host``
* tries to read ``user_id`` from the JSON body (planning routes) or query
  params (fallback)
* consumes one token from each applicable bucket
* increments the concurrency counter
* on response (or exception), decrements the concurrency counter

Tests construct their own ``RateLimiter`` and override the module-level
``_LIMITER`` via :func:`set_limiter` so they get a fresh state per test and can
control the clock.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, Optional

from fastapi import HTTPException, Request


__all__ = [
    "RateLimiter",
    "RouteLimits",
    "RateLimitExceeded",
    "DEFAULT_LIMITS",
    "get_limiter",
    "set_limiter",
    "limit",
]


# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RouteLimits:
    """Limits for a single named route.

    ``per_minute_*`` is the bucket capacity *and* the refill rate per 60s.
    ``max_concurrent_per_user`` caps in-flight jobs per user_id.
    """

    per_minute_ip: int
    per_minute_user: int
    max_concurrent_per_user: int


# Defaults match the rate-limit spec in the security review:
#   /api/plan           — 10/min per IP, 20/min per user, max 2 concurrent
#   /api/four-year-plan —  5/min per IP, 10/min per user, max 1 concurrent
#   /api/workday/sync   —  2/min per IP,  3/min per user, max 1 concurrent
DEFAULT_LIMITS: Dict[str, RouteLimits] = {
    "plan": RouteLimits(per_minute_ip=10, per_minute_user=20, max_concurrent_per_user=2),
    "four_year_plan": RouteLimits(per_minute_ip=5, per_minute_user=10, max_concurrent_per_user=1),
    "workday_sync": RouteLimits(per_minute_ip=2, per_minute_user=3, max_concurrent_per_user=1),
}


# ── Token bucket ──────────────────────────────────────────────────────────────


@dataclass
class _Bucket:
    """A classic token bucket.

    ``capacity`` is the maximum number of tokens.
    ``refill_per_sec`` is the rate at which tokens are added.
    ``tokens`` is the current (fractional) token balance.
    ``updated`` is the last clock reading we refilled against.
    """

    capacity: float
    refill_per_sec: float
    tokens: float
    updated: float

    def try_consume(self, now: float, amount: float = 1.0) -> tuple[bool, float]:
        """Attempt to consume ``amount`` tokens.

        Returns ``(allowed, retry_after_seconds)``. ``retry_after_seconds`` is
        ``0.0`` on success and the time until the bucket has enough tokens on
        failure (rounded up to at least 1 second so clients always wait *some*
        sensible interval before retrying).
        """
        # Refill: add tokens proportional to elapsed wall-clock time, clamped
        # at capacity so we never accumulate burst capacity beyond the cap.
        elapsed = max(0.0, now - self.updated)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.updated = now

        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0.0

        # Not enough tokens — figure out how long until we have ``amount``.
        deficit = amount - self.tokens
        if self.refill_per_sec <= 0:
            # Defensive: a misconfigured bucket can't refill, so the wait is
            # effectively forever. Return a large but finite value.
            return False, 60.0
        wait = deficit / self.refill_per_sec
        # Round *up* to a whole second — HTTP Retry-After is an integer field.
        return False, max(1.0, float(int(wait) + (1 if wait > int(wait) else 0)))


# ── Limiter ───────────────────────────────────────────────────────────────────


class RateLimitExceeded(HTTPException):
    """429 with a structured body distinct from "no transcript" 400s."""

    def __init__(self, scope: str, retry_after: int) -> None:
        super().__init__(
            status_code=429,
            detail={
                "error": "rate_limited",
                "retry_after_seconds": retry_after,
                "scope": scope,
            },
            headers={"Retry-After": str(retry_after)},
        )


class RateLimiter:
    """Thread-safe, in-memory token-bucket + concurrency limiter.

    The clock is injectable so tests can simulate time passing without sleeping.
    """

    def __init__(
        self,
        limits: Optional[Dict[str, RouteLimits]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits: Dict[str, RouteLimits] = dict(limits or DEFAULT_LIMITS)
        self._clock = clock
        self._lock = threading.Lock()
        # Keyed by (route, scope, identity) -> Bucket. Separate buckets per
        # scope ensures that two different IPs (or users) never share state.
        self._buckets: Dict[tuple[str, str, str], _Bucket] = {}
        # Keyed by (route, user_id) -> int (in-flight count).
        self._concurrent: Dict[tuple[str, str], int] = {}

    # ── Public configuration ──────────────────────────────────────────────────

    def configure(self, route: str, limits: RouteLimits) -> None:
        """Add or replace limits for a named route (mainly for tests)."""
        with self._lock:
            self._limits[route] = limits

    def limits_for(self, route: str) -> RouteLimits:
        try:
            return self._limits[route]
        except KeyError as exc:  # pragma: no cover - configuration bug
            raise KeyError(f"No rate limits configured for route {route!r}") from exc

    # ── Bucket helpers ────────────────────────────────────────────────────────

    def _get_bucket(
        self, route: str, scope: str, identity: str, capacity: int
    ) -> _Bucket:
        """Look up or lazily create a bucket. Must be called under the lock."""
        key = (route, scope, identity)
        bucket = self._buckets.get(key)
        if bucket is None:
            # Per-minute semantics: capacity tokens, refilled smoothly over 60s.
            refill = capacity / 60.0 if capacity > 0 else 0.0
            bucket = _Bucket(
                capacity=float(capacity),
                refill_per_sec=refill,
                tokens=float(capacity),
                updated=self._clock(),
            )
            self._buckets[key] = bucket
        return bucket

    # ── Core check ────────────────────────────────────────────────────────────

    def check(self, route: str, ip: str, user_id: Optional[str]) -> None:
        """Raise :class:`RateLimitExceeded` if any scope rejects the request.

        Token consumption is applied atomically across both rate scopes: if
        either scope would reject, neither bucket is debited. This way a
        legitimately rate-limited user doesn't also burn through their IP
        bucket (and vice versa).
        """
        limits = self.limits_for(route)
        now = self._clock()

        with self._lock:
            ip_bucket = self._get_bucket(route, "ip", ip, limits.per_minute_ip)
            user_bucket = (
                self._get_bucket(route, "user", user_id, limits.per_minute_user)
                if user_id
                else None
            )

            # Refill *both* buckets first (a zero-amount consume still refills
            # the bucket against the current clock reading) so the
            # availability check below sees up-to-date token balances.
            ip_bucket.try_consume(now, amount=0.0)
            if user_bucket is not None:
                user_bucket.try_consume(now, amount=0.0)

            # Decide rejection *before* debiting. IP scope takes priority over
            # user scope — a flood from one machine is the higher-severity
            # signal and the more likely abuse pattern.
            if ip_bucket.tokens < 1.0:
                _, retry = ip_bucket.try_consume(now, amount=1.0)
                raise RateLimitExceeded("ip", int(retry))
            if user_bucket is not None and user_bucket.tokens < 1.0:
                _, retry = user_bucket.try_consume(now, amount=1.0)
                raise RateLimitExceeded("user", int(retry))

            # Both scopes have at least one token — commit consumption.
            ip_bucket.try_consume(now, amount=1.0)
            if user_bucket is not None:
                user_bucket.try_consume(now, amount=1.0)

    # ── Concurrency ───────────────────────────────────────────────────────────

    @contextmanager
    def acquire_slot(self, route: str, user_id: Optional[str]) -> Iterator[None]:
        """Reserve a concurrency slot for the duration of the request.

        If ``user_id`` is missing we can't meaningfully cap concurrency
        per-user (there's no key to count against), so we simply yield without
        accounting. This is intentional — the rate-per-IP bucket already
        provides a per-source ceiling and the typical attack vector is an
        authenticated user spamming regenerate.
        """
        if not user_id:
            yield
            return

        limits = self.limits_for(route)
        key = (route, user_id)
        with self._lock:
            current = self._concurrent.get(key, 0)
            if current >= limits.max_concurrent_per_user:
                # 30s is a sensible default retry window for a slow agent run.
                raise RateLimitExceeded("concurrency", 30)
            self._concurrent[key] = current + 1

        try:
            yield
        finally:
            with self._lock:
                n = self._concurrent.get(key, 0)
                if n <= 1:
                    self._concurrent.pop(key, None)
                else:
                    self._concurrent[key] = n - 1


# ── Module-level limiter + test overrides ─────────────────────────────────────


_LIMITER: RateLimiter = RateLimiter()


def get_limiter() -> RateLimiter:
    """Return the module-wide limiter (overridable in tests via ``set_limiter``)."""
    return _LIMITER


def set_limiter(limiter: RateLimiter) -> None:
    """Replace the module-wide limiter — intended for test fixtures."""
    global _LIMITER
    _LIMITER = limiter


# ── FastAPI dependency factory ────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Falls back to ``unknown`` when behind weird
    test transports that don't populate ``request.client``."""
    # Honour the first hop of X-Forwarded-For when present so the limiter
    # still works behind a single trusted proxy. We deliberately do *not*
    # trust deeper hops since they're forgeable.
    fwd = request.headers.get("x-forwarded-for", "").strip()
    if fwd:
        first = fwd.split(",", 1)[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _extract_user_id(request: Request) -> Optional[str]:
    """Pull ``user_id`` from JSON body (cached so route handler can re-read)
    or from query params. Returns ``None`` if absent or unparseable."""
    # Try query param first — cheap, no body consumption.
    q = request.query_params.get("user_id")
    if q and q.strip():
        return q.strip()

    # Then try JSON body. FastAPI caches body bytes on the request so this
    # doesn't break the downstream Pydantic model parsing.
    try:
        body_bytes = await request.body()
    except Exception:  # noqa: BLE001
        return None
    if not body_bytes:
        return None
    try:
        import json

        parsed: Any = json.loads(body_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(parsed, dict):
        uid = parsed.get("user_id")
        if isinstance(uid, str) and uid.strip():
            return uid.strip()
    return None


def limit(route: str) -> Callable[..., Any]:
    """Build a FastAPI dependency that enforces ``route``'s limits.

    Returns a *yield dependency*: the code before ``yield`` runs before the
    route handler (consuming tokens and reserving a concurrency slot); the
    code after ``yield`` runs after the handler returns (or raises), releasing
    the concurrency slot.

    Failures raise :class:`RateLimitExceeded` (HTTP 429) with a structured
    body so the frontend can tell rate-limit errors apart from validation
    errors.
    """

    async def _dep(request: Request) -> Any:
        limiter = get_limiter()
        ip = _client_ip(request)
        user_id = await _extract_user_id(request)

        # Rate-limit check first (cheap). If this raises, no slot is acquired.
        limiter.check(route, ip, user_id)

        # Concurrency slot scoped to the request lifetime. The yield
        # dependency contract ensures the ``finally`` block runs even if the
        # route handler raises, so we never leak slots.
        with limiter.acquire_slot(route, user_id):
            yield

    return _dep
