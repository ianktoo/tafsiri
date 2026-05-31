import requests

from tafsiri.providers.daraja import DarajaTranslator


class FakeResponse:
    def __init__(self, status=200, payload=None, text="", raise_json=False, headers=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.text = text
        self._raise_json = raise_json
        self.headers = headers or {}

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.last_call = None
        self.calls = 0

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_call = {"url": url, "headers": headers, "json": json}
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.response


class SequenceSession:
    """Returns a queued response per call, to exercise retry behavior."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, *a, **kw):
        self.calls += 1
        return self.responses.pop(0)


def _translator(session, **kw):
    # no real sleeping in tests
    return DarajaTranslator("dk_test", session=session, sleep=lambda s: None, **kw)


def test_successful_translation():
    session = FakeSession(FakeResponse(200, {
        "translation": "habari", "confidence": 0.91, "model": "babel-sw-v1"}))
    tr = _translator(session).translate("hello", "English", "Swahili")
    assert tr.ok
    assert tr.text == "habari"
    assert tr.confidence == 0.91
    assert tr.model == "babel-sw-v1"
    # request shaped correctly
    assert session.last_call["json"] == {"text": "hello", "from": "English", "to": "Swahili"}
    assert session.last_call["headers"]["Authorization"] == "Bearer dk_test"


def test_http_error_is_captured_not_raised():
    session = FakeSession(FakeResponse(401, {"error": "unauthorized"}))
    tr = _translator(session).translate("hello", "English", "Swahili")
    assert not tr.ok
    assert "401" in tr.error


def test_non_json_response():
    session = FakeSession(FakeResponse(200, text="<html>blocked</html>", raise_json=True))
    tr = _translator(session).translate("hello", "English", "Swahili")
    assert not tr.ok
    assert "non-JSON" in tr.error


def test_request_exception_is_captured():
    session = FakeSession(exc=requests.ConnectionError("boom"))
    tr = _translator(session).translate("hello", "English", "Swahili")
    assert not tr.ok
    assert "request failed" in tr.error


def test_missing_translation_field():
    session = FakeSession(FakeResponse(200, {"confidence": 0.5}))
    tr = _translator(session).translate("hello", "English", "Swahili")
    assert not tr.ok
    assert "no translation field" in tr.error


def test_retries_on_429_then_succeeds():
    session = SequenceSession([
        FakeResponse(429, text="Too many requests", raise_json=True),
        FakeResponse(429, text="Too many requests", raise_json=True),
        FakeResponse(200, {"translation": "habari", "confidence": 0.9}),
    ])
    tr = _translator(session, max_retries=4).translate("hello", "English", "Swahili")
    assert tr.ok
    assert tr.text == "habari"
    assert session.calls == 3  # two 429s, then success


def test_gives_up_after_max_retries():
    session = SequenceSession([FakeResponse(429, text="rl", raise_json=True)] * 3)
    tr = _translator(session, max_retries=2).translate("hello", "English", "Swahili")
    assert not tr.ok
    assert "429" in tr.error
    assert session.calls == 3  # initial + 2 retries


def test_does_not_retry_on_401():
    session = SequenceSession([FakeResponse(401, {"error": "unauthorized"})])
    tr = _translator(session, max_retries=4).translate("hello", "English", "Swahili")
    assert not tr.ok
    assert session.calls == 1  # auth errors are not retried
