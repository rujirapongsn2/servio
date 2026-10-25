import asyncio
import copy
import json

import httpx
import pytest

from app.intent_contract import DECISION_PROFILE, INTENT_COLORS
from app.intent_decision import classify_intent


GROUP = "Smooth Resolution"
HISTORY = [{"role": "user", "content": "ใช้งานได้แล้วครับ"}]


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    for name in (
        "ENABLED", "BASE_URL", "API_KEY", "TIMEOUT_SECONDS",
        "MIN_CONFIDENCE", "MIN_PROBABILITY", "MIN_MARGIN",
    ):
        monkeypatch.delenv("INTENT_DECISION_" + name, raising=False)
    monkeypatch.setenv("INTENT_DECISION_ENABLED", "true")
    monkeypatch.setenv("INTENT_DECISION_BASE_URL", "http://decision.local:8091")
    monkeypatch.setenv("INTENT_DECISION_API_KEY", "dedicated-key")


def response():
    return {
        "schema_version": 1,
        "profile": DECISION_PROFILE,
        "selected_key": GROUP,
        "confidence": .9,
        "probabilities": {group: .9 if group == GROUP else .025 for group in INTENT_COLORS},
    }


def classify(payload=None, *, history=None, status=200):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=response() if payload is None else payload)

    result = asyncio.run(classify_intent(
        HISTORY if history is None else history, transport=httpx.MockTransport(handler),
    ))
    return result, calls


def test_accepted_result_sends_dedicated_auth_and_versioned_context():
    result, calls = classify()
    assert result == GROUP
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "http://decision.local:8091/v1/intent"
    assert request.method == "POST"
    assert request.headers["authorization"] == "Bearer dedicated-key"
    assert json.loads(request.content) == {
        "schema_version": 1, "context": "user: ใช้งานได้แล้วครับ",
    }


@pytest.mark.parametrize("name,value", [
    ("ENABLED", None), ("ENABLED", "false"), ("ENABLED", "yes"),
    ("API_KEY", None), ("API_KEY", ""), ("API_KEY", " key"),
    ("API_KEY", "key\r\nsecret"), ("API_KEY", "คีย์"),
    ("BASE_URL", None), ("BASE_URL", "ftp://decision.local"),
    ("BASE_URL", "http://"), ("BASE_URL", "http://user:secret@decision.local"),
    ("BASE_URL", "http://decision.local?secret=x"),
    ("BASE_URL", "http://decision.local#fragment"),
    ("BASE_URL", "http://decision.local?"), ("BASE_URL", "http://decision.local#"),
    ("BASE_URL", "http://decision.local:99999"),
    ("BASE_URL", "http://decision.local/ bad"),
    ("BASE_URL", "http://decision.local\\evil"),
    ("TIMEOUT_SECONDS", "0.099"), ("TIMEOUT_SECONDS", "5.001"),
    ("TIMEOUT_SECONDS", "nan"), ("TIMEOUT_SECONDS", "inf"),
    ("TIMEOUT_SECONDS", "oops"),
    ("MIN_CONFIDENCE", "-0.01"), ("MIN_CONFIDENCE", "1.01"),
    ("MIN_PROBABILITY", "nan"), ("MIN_PROBABILITY", "1.01"),
    ("MIN_MARGIN", "inf"), ("MIN_MARGIN", "-1"),
])
def test_invalid_or_disabled_configuration_never_calls_http(monkeypatch, name, value):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    if value is None:
        monkeypatch.delenv("INTENT_DECISION_" + name, raising=False)
    else:
        monkeypatch.setenv("INTENT_DECISION_" + name, value)
    assert classify() == (None, [])


@pytest.mark.parametrize("history", [
    [], [{"role": "assistant", "content": "hello"}],
    [{"role": "user", "content": ""}], [{"role": "user", "content": "  \n"}],
    [{"role": "user", "content": [{"type": "text", "text": "private"}]}],
    HISTORY + [{"role": "user", "content": None}],
    HISTORY + [{"role": "user", "content": {"secret": "private"}}],
    HISTORY + [{"role": "assistant", "content": "x"}] * 6,
    [{"role": "user", "content": "\ud800"}], None, {}, "private",
])
def test_missing_latest_plain_user_text_abstains_without_http(history):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    assert asyncio.run(classify_intent(history, transport=httpx.MockTransport(handler))) is None
    assert calls == []


def test_context_contains_only_recent_conversation_text_without_metadata():
    history = [
        {"role": "user", "content": "old private text"},
        {"role": "system", "content": "system secret"},
        {"role": "tool", "content": "tool secret"},
        {"role": "assistant", "content": "recent answer", "tool_calls": ["secret"]},
        {"role": "assistant", "content": [{"image_url": "secret"}]},
        {"role": "developer", "content": "developer secret"},
        {"role": "user", "content": "new question", "metadata": "secret"},
    ]
    original = copy.deepcopy(history)
    result, calls = classify(history=history)
    assert result == GROUP
    assert json.loads(calls[0].content) == {
        "schema_version": 1, "context": "assistant: recent answer\nuser: new question",
    }
    assert history == original


@pytest.mark.parametrize("text,accepted", [
    ("x" * 2042, True), ("x" * 2043, False),
    ("ก" * 680 + "xx", True), ("ก" * 681, False),
])
def test_context_byte_limit_abstains_instead_of_truncating(text, accepted):
    result, calls = classify(history=[{"role": "user", "content": text}])
    assert result == (GROUP if accepted else None)
    assert len(calls) == int(accepted)
    if accepted:
        assert json.loads(calls[0].content)["context"] == "user: " + text


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", "1"), ("schema_version", 1.0),
    ("schema_version", 2), ("profile", "stale"), ("profile", None),
    ("selected_key", "unknown"), ("selected_key", list(INTENT_COLORS)[1]),
    ("selected_key", []), ("confidence", True), ("confidence", ".99"),
    ("confidence", None), ("confidence", float("nan")),
    ("confidence", float("inf")), ("confidence", -0.1), ("confidence", 1.1),
    ("probabilities", []), ("probabilities", None),
])
def test_malformed_response_fields_abstain(field, value):
    payload = response()
    payload[field] = value
    assert classify(payload)[0] is None


@pytest.mark.parametrize("field", list(response()))
def test_missing_required_field_abstains(field):
    payload = response()
    del payload[field]
    assert classify(payload)[0] is None


def test_extra_response_field_abstains():
    assert classify({**response(), "action": "handoff"})[0] is None


@pytest.mark.parametrize("payload", [[], "Smooth Resolution", 1, True])
def test_nonobject_responses_abstain(payload):
    assert classify(payload)[0] is None


@pytest.mark.parametrize("value", [True, False, "0.9", None, float("nan"), float("inf"), -1, 1.1, 10**400])
def test_invalid_probabilities_abstain(value):
    payload = response()
    payload["probabilities"][GROUP] = value
    assert classify(payload)[0] is None


@pytest.mark.parametrize("change", ["missing", "unknown", "sum", "tie", "wrong_winner"])
def test_distribution_must_be_complete_normalized_with_unique_correct_winner(change):
    payload = response()
    probabilities = payload["probabilities"]
    other = list(INTENT_COLORS)[1]
    if change == "missing":
        del probabilities[other]
    elif change == "unknown":
        probabilities["unknown"] = probabilities.pop(other)
    elif change == "sum":
        probabilities[GROUP] = .95
    elif change == "tie":
        probabilities.update({group: .5 if group in (GROUP, other) else 0 for group in INTENT_COLORS})
    else:
        probabilities[GROUP], probabilities[other] = probabilities[other], probabilities[GROUP]
    assert classify(payload)[0] is None


@pytest.mark.parametrize("confidence,top,accepted", [
    (.75, .85, True), (.7499, .9, False), (.9, .8499, False), (.9, .9, True),
])
def test_default_confidence_and_probability_gates(confidence, top, accepted):
    payload = response()
    payload["confidence"] = confidence
    payload["probabilities"] = {group: top if group == GROUP else (1 - top) / 4 for group in INTENT_COLORS}
    assert classify(payload)[0] == (GROUP if accepted else None)


@pytest.mark.parametrize("margin,accepted", [(".5", True), (".5001", False)])
def test_margin_gate_is_independent_and_inclusive(monkeypatch, margin, accepted):
    monkeypatch.setenv("INTENT_DECISION_MIN_PROBABILITY", ".5")
    monkeypatch.setenv("INTENT_DECISION_MIN_MARGIN", margin)
    payload = response()
    payload["probabilities"] = dict.fromkeys(INTENT_COLORS, 0)
    payload["probabilities"][GROUP] = .75
    payload["probabilities"][list(INTENT_COLORS)[1]] = .25
    assert classify(payload)[0] == (GROUP if accepted else None)


@pytest.mark.parametrize("threshold", ["0", "1"])
def test_threshold_configuration_accepts_inclusive_bounds(monkeypatch, threshold):
    for name in ("MIN_CONFIDENCE", "MIN_PROBABILITY", "MIN_MARGIN"):
        monkeypatch.setenv("INTENT_DECISION_" + name, threshold)
    payload = response()
    payload["confidence"] = 1
    payload["probabilities"] = {group: int(group == GROUP) for group in INTENT_COLORS}
    assert classify(payload)[0] == GROUP


@pytest.mark.parametrize("deviation,accepted", [(.0009, True), (.0011, False), (-.0009, True), (-.0011, False)])
def test_distribution_sum_tolerance(deviation, accepted):
    payload = response()
    payload["probabilities"][GROUP] += deviation
    assert classify(payload)[0] == (GROUP if accepted else None)


@pytest.mark.parametrize("timeout", [".1", "5"])
def test_timeout_configuration_accepts_inclusive_bounds(monkeypatch, timeout):
    monkeypatch.setenv("INTENT_DECISION_TIMEOUT_SECONDS", timeout)
    assert classify()[0] == GROUP


@pytest.mark.parametrize("status", [301, 302, 307, 401, 403, 413, 429, 500, 503])
def test_http_failures_and_redirects_abstain_without_retry(status):
    result, calls = classify(status=status)
    assert result is None
    assert len(calls) == 1


@pytest.mark.parametrize("body", [
    b"not json", b"\xff", b"null", b"{}", b'{"schema_version":1,"schema_version":1}',
    pytest.param(b"[" * 1500 + b"]" * 1500, id="deeply-nested-json"),
])
def test_invalid_json_abstains(body):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    assert asyncio.run(classify_intent(HISTORY, transport=transport)) is None


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_fields_in_otherwise_valid_reply_abstain(nested):
    body = json.dumps(response())
    if nested:
        body = body.replace('"probabilities": {', '"probabilities": {"Smooth Resolution": 0.9, ')
    else:
        body = body[:-1] + ', "schema_version": 1}'
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    assert asyncio.run(classify_intent(HISTORY, transport=transport)) is None


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_network_failures_abstain_without_retry(error):
    calls = []

    def handler(request):
        calls.append(request)
        raise error("unavailable")

    assert asyncio.run(classify_intent(HISTORY, transport=httpx.MockTransport(handler))) is None
    assert len(calls) == 1


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.closed = False
        self.reads = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            self.reads += 1
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("size,accepted", [(8192, True), (8193, False)])
def test_streamed_response_byte_limit_and_cleanup(size, accepted):
    body = json.dumps(response()).encode()
    stream = Chunks([body, b" " * (size - len(body)), b""])
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    assert asyncio.run(classify_intent(HISTORY, transport=transport)) == (GROUP if accepted else None)
    assert stream.closed
    if not accepted:
        assert stream.reads == 2


def test_total_deadline_covers_partial_stream_not_just_each_read(monkeypatch):
    monkeypatch.setenv("INTENT_DECISION_TIMEOUT_SECONDS", ".1")
    stream = Chunks([b"{", b" ", b" "], delay=.04)
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))

    async def run():
        return await asyncio.wait_for(classify_intent(HISTORY, transport=transport), timeout=.5)

    assert asyncio.run(run()) is None
    assert stream.closed
    assert 0 < stream.reads < 3


def test_total_deadline_covers_waiting_for_response_headers(monkeypatch):
    monkeypatch.setenv("INTENT_DECISION_TIMEOUT_SECONDS", ".1")
    cancelled = []

    async def handler(_):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return httpx.Response(200, json=response())

    async def run():
        return await asyncio.wait_for(
            classify_intent(HISTORY, transport=httpx.MockTransport(handler)), timeout=.5,
        )

    assert asyncio.run(run()) is None
    assert cancelled == [True]


def test_caller_cancellation_propagates_and_closes_stream():
    stream = Chunks([b"{"], delay=10)
    started = None

    async def run():
        nonlocal started
        started = asyncio.Event()

        def handler(_):
            started.set()
            return httpx.Response(200, stream=stream)

        task = asyncio.create_task(classify_intent(HISTORY, transport=httpx.MockTransport(handler)))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert stream.closed


def test_secrets_and_context_are_not_logged(caplog):
    assert classify(status=503)[0] is None
    assert "dedicated-key" not in caplog.text
    assert HISTORY[0]["content"] not in caplog.text
