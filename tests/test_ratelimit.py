from tafsiri.ratelimit import RateLimiter, RateLimitedTranslator

from conftest import FakeTranslator


def test_rate_limiter_spaces_acquisitions():
    clock = {"t": 0.0}
    slept: list[float] = []
    rl = RateLimiter(min_interval=2.0,
                     sleep=lambda s: slept.append(s),
                     clock=lambda: clock["t"])
    rl.acquire()              # first is immediate
    rl.acquire()              # must wait 2.0 (no time has passed)
    rl.acquire()              # must wait 4.0 total scheduling
    assert slept == [2.0, 4.0]


def test_rate_limiter_disabled_when_zero():
    slept = []
    rl = RateLimiter(0, sleep=lambda s: slept.append(s))
    rl.acquire(); rl.acquire()
    assert slept == []


def test_rate_limited_translator_acquires_then_delegates():
    calls = []
    inner = FakeTranslator()
    rl = RateLimiter(1.0, sleep=lambda s: calls.append(("sleep", s)),
                     clock=lambda: 0.0)
    t = RateLimitedTranslator(inner, rl)
    t.translate("hello", "English", "Swahili")
    t.translate("bye", "English", "Swahili")
    assert t.name == inner.name
    assert inner.calls == [("hello", "English", "Swahili"),
                           ("bye", "English", "Swahili")]
    # second call had to wait
    assert ("sleep", 1.0) in calls
