"""Tests for the in-memory rate limiter (token bucket + concurrency).

Pins the contract the red-team review asked for:

  * Per-IP and per-user rate limits with independent buckets
  * Per-user concurrency cap on expensive routes
  * HTTP 429 + ``Retry-After`` header + structured body distinguishing
    rate_limited from ip/user/concurrency scope (so the frontend never
    confuses this with the "no transcript loaded" 400 error)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the api package importable without uvicorn
_API = Path(__file__).resolve().parents[2] / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from middleware.rate_limit import (  # noqa: E402
    DEFAULT_LIMITS,
    RateLimitExceeded,
    RateLimiter,
    RouteLimits,
)


# ── Token-bucket core ────────────────────────────────────────────────────────


@pytest.fixture
def clock() -> list[float]:
    """Mutable mono-time backing for the limiter — tests advance it directly."""
    return [0.0]


@pytest.fixture
def limiter(clock):
    """A limiter with tiny test limits so behaviour is easy to assert."""
    return RateLimiter(
        limits={
            "plan": RouteLimits(per_minute_ip=3, per_minute_user=5, max_concurrent_per_user=2),
            "four_year_plan": RouteLimits(per_minute_ip=2, per_minute_user=4, max_concurrent_per_user=1),
        },
        clock=lambda: clock[0],
    )


def test_first_request_passes(limiter):
    limiter.check("plan", ip="1.1.1.1", user_id="u1")  # no raise


def test_per_ip_bucket_rejects_overflow(limiter):
    """Three requests fit; the fourth raises with scope='ip'."""
    for _ in range(3):
        limiter.check("plan", ip="1.1.1.1", user_id="u1")
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.check("plan", ip="1.1.1.1", user_id="u1")
    assert exc.value.status_code == 429
    assert exc.value.detail["error"] == "rate_limited"
    assert exc.value.detail["scope"] == "ip"
    assert exc.value.detail["retry_after_seconds"] >= 1
    assert exc.value.headers["Retry-After"] == str(exc.value.detail["retry_after_seconds"])


def test_per_user_scope_rejects_when_ip_unlimited(limiter, clock):
    """Send 6 requests from 6 different IPs but same user; user cap fires on the 6th."""
    for i in range(5):
        limiter.check("plan", ip=f"10.0.0.{i}", user_id="alice")
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.check("plan", ip="10.0.0.99", user_id="alice")
    assert exc.value.detail["scope"] == "user"


def test_different_ips_do_not_share_buckets(limiter):
    """A flood from one IP must not exhaust another IP's quota."""
    for _ in range(3):
        limiter.check("plan", ip="1.1.1.1", user_id=None)
    # Different IP — fresh bucket
    for _ in range(3):
        limiter.check("plan", ip="2.2.2.2", user_id=None)


def test_different_users_do_not_share_buckets(limiter):
    """Two different user_ids each get the full per-user quota.

    Spread requests across unique IPs to avoid tripping the per-IP cap
    (3/min in this fixture) before we hit the per-user cap (5/min)."""
    for i in range(5):
        limiter.check("plan", ip=f"10.0.0.{i}", user_id="alice")
    for i in range(5):
        limiter.check("plan", ip=f"10.1.0.{i}", user_id="bob")


def test_bucket_refills_over_time(limiter, clock):
    """After 60s, a full bucket is available again."""
    for _ in range(3):
        limiter.check("plan", ip="1.1.1.1", user_id="u1")
    with pytest.raises(RateLimitExceeded):
        limiter.check("plan", ip="1.1.1.1", user_id="u1")

    clock[0] += 60  # full minute → bucket refilled
    limiter.check("plan", ip="1.1.1.1", user_id="u1")  # no raise


def test_anonymous_request_skips_user_bucket(limiter):
    """user_id=None → only the IP bucket gates; user bucket isn't created."""
    for _ in range(3):
        limiter.check("plan", ip="1.1.1.1", user_id=None)
    # User bucket has never been touched — verify no key was inserted
    assert not any(scope == "user" for (_, scope, _) in limiter._buckets.keys())


def test_route_isolation(limiter):
    """Hitting ``plan``'s IP cap doesn't reject ``four_year_plan``."""
    for _ in range(3):
        limiter.check("plan", ip="1.1.1.1", user_id="u1")
    with pytest.raises(RateLimitExceeded):
        limiter.check("plan", ip="1.1.1.1", user_id="u1")
    # Different route, same identity → still has budget
    limiter.check("four_year_plan", ip="1.1.1.1", user_id="u1")
    limiter.check("four_year_plan", ip="1.1.1.1", user_id="u1")


# ── Concurrency ───────────────────────────────────────────────────────────────


def test_concurrency_cap_fires(limiter):
    """Two in-flight slots allowed for ``plan``; the third raises."""
    cm1 = limiter.acquire_slot("plan", "alice")
    cm2 = limiter.acquire_slot("plan", "alice")
    cm1.__enter__()
    cm2.__enter__()
    try:
        with pytest.raises(RateLimitExceeded) as exc:
            with limiter.acquire_slot("plan", "alice"):
                pass
        assert exc.value.detail["scope"] == "concurrency"
    finally:
        cm2.__exit__(None, None, None)
        cm1.__exit__(None, None, None)


def test_concurrency_slot_released_on_normal_exit(limiter):
    """Slot is released when the context manager exits cleanly."""
    with limiter.acquire_slot("plan", "alice"):
        pass
    with limiter.acquire_slot("plan", "alice"):
        pass  # no exception — slot was returned


def test_concurrency_slot_released_on_exception(limiter):
    """Slot is released even if the request handler raises."""
    with pytest.raises(RuntimeError):
        with limiter.acquire_slot("plan", "alice"):
            raise RuntimeError("handler blew up")
    # Slot must be free again
    with limiter.acquire_slot("plan", "alice"):
        pass


def test_concurrency_per_user_isolation(limiter):
    """Alice and Bob each get their own concurrency budget."""
    with limiter.acquire_slot("plan", "alice"):
        with limiter.acquire_slot("plan", "alice"):
            # Alice is at 2/2. Bob still has 2 slots free.
            with limiter.acquire_slot("plan", "bob"):
                pass


def test_anonymous_concurrency_is_unbounded(limiter):
    """user_id=None can't be counted, so concurrency is not enforced —
    falls back to per-IP rate limiting instead."""
    cms = [limiter.acquire_slot("plan", None) for _ in range(10)]
    for c in cms:
        c.__enter__()
    for c in cms:
        c.__exit__(None, None, None)


# ── Defaults match the security review spec ──────────────────────────────────


def test_default_limits_match_review_spec():
    """The defaults shipped in DEFAULT_LIMITS must match the red-team review:
    plan 10/min IP + 20/min user + 2 concurrent;
    four_year_plan 5/min + 10/min + 1; workday_sync 2/min + 3/min + 1."""
    assert DEFAULT_LIMITS["plan"].per_minute_ip == 10
    assert DEFAULT_LIMITS["plan"].per_minute_user == 20
    assert DEFAULT_LIMITS["plan"].max_concurrent_per_user == 2

    assert DEFAULT_LIMITS["four_year_plan"].per_minute_ip == 5
    assert DEFAULT_LIMITS["four_year_plan"].per_minute_user == 10
    assert DEFAULT_LIMITS["four_year_plan"].max_concurrent_per_user == 1

    assert DEFAULT_LIMITS["workday_sync"].per_minute_ip == 2
    assert DEFAULT_LIMITS["workday_sync"].per_minute_user == 3
    assert DEFAULT_LIMITS["workday_sync"].max_concurrent_per_user == 1
