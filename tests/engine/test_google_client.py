"""Google keys: Gemini API first, Vertex AI second, remember what works."""

import pytest

from openjarvis.engine.google_client import SwitchingClient, wrong_service

DISABLED = RuntimeError(
    "403 PERMISSION_DENIED. Agent Platform API has not been used in project 8011 "
    "before or it is disabled."
)


class Fake:
    def __init__(self, vertex, behaviour, calls):
        self.vertex, self.behaviour, self.calls = vertex, behaviour, calls
        self.models = self

    def generate_content(self, **kw):
        self.calls.append(("gen", self.vertex))
        result = self.behaviour[self.vertex]
        if isinstance(result, Exception):
            raise result
        return result

    def generate_content_stream(self, **kw):
        self.calls.append(("stream", self.vertex))
        result = self.behaviour[self.vertex]

        def gen():
            if isinstance(result, Exception):
                raise result
            yield from result

        return gen()


def _client(behaviour):
    calls = []
    return (
        SwitchingClient(
            "AQ.k", factory=lambda key, vertex: Fake(vertex, behaviour, calls)
        ),
        calls,
    )


def test_gemini_api_first():
    client, calls = _client({False: "hola", True: "vertex"})
    assert client.models.generate_content(model="m") == "hola"
    assert calls == [("gen", False)] and client.vertex is False


def test_falls_back_to_vertex_and_remembers():
    client, calls = _client({False: RuntimeError("400 API key not valid"), True: "ok"})
    assert client.models.generate_content(model="m") == "ok"
    assert client.models.generate_content(model="m") == "ok"
    assert calls == [("gen", False), ("gen", True), ("gen", True)]
    assert client.vertex is True


def test_vertex_disabled_uses_gemini_api():
    client, _ = _client({False: "hola", True: DISABLED})
    client._modes = [True, False]  # e.g. remembered from before
    assert client.models.generate_content(model="m") == "hola"
    assert client.vertex is False


def test_stream_switches_on_first_chunk():
    client, calls = _client({False: DISABLED, True: ["a", "b"]})
    assert list(client.models.generate_content_stream(model="m")) == ["a", "b"]
    assert calls == [("stream", False), ("stream", True)]


def test_both_services_refuse_explains_how_to_fix():
    client, _ = _client({False: DISABLED, True: DISABLED})
    with pytest.raises(RuntimeError, match="aistudio.google.com/apikey"):
        client.models.generate_content(model="m")


def test_real_errors_are_not_hidden():
    client, calls = _client({False: ValueError("bad prompt"), True: "x"})
    with pytest.raises(ValueError):
        client.models.generate_content(model="m")
    assert calls == [("gen", False)]
    assert wrong_service(DISABLED) and not wrong_service(ValueError("timeout"))


def test_a_spent_model_is_not_asked_again_until_its_quota_returns(monkeypatch):
    from openjarvis.engine import google_client as gc

    monkeypatch.setattr(gc, "_EXHAUSTED", {})
    spent = RuntimeError(
        "429 RESOURCE_EXHAUSTED. You exceeded your current quota ... "
        "GenerateRequestsPerDayPerProjectPerModel-FreeTier ... Please retry in 1h37m1.3s."
    )
    client, calls = _client({False: spent, True: spent})
    with pytest.raises(RuntimeError):
        client.models.generate_content(model="gemini-3.8-flash-tts", contents="hola")
    assert len(calls) == 1
    with pytest.raises(gc.QuotaExhausted, match="RESOURCE_EXHAUSTED"):
        client.models.generate_content(model="gemini-3.8-flash-tts", contents="hola")
    assert len(calls) == 1  # answered at once, no request
    assert 5800 < gc._EXHAUSTED["gemini-3.8-flash-tts"] - gc.time.monotonic() < 5830
    client2, calls2 = _client({False: "ok", True: "ok"})
    assert client2.models.generate_content(model="gemini-3.8-flash", contents="x") == "ok"


def test_an_overloaded_model_is_skipped_for_a_moment(monkeypatch):
    from openjarvis.engine import google_client as gc

    monkeypatch.setattr(gc, "_EXHAUSTED", {})
    busy = RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")
    client, calls = _client({False: busy, True: busy})
    with pytest.raises(RuntimeError):
        client.models.generate_content(model="gemini-3.8-flash", contents="x")
    with pytest.raises(gc.QuotaExhausted):
        client.models.generate_content(model="gemini-3.8-flash", contents="x")
    assert len(calls) == 1
    assert gc._EXHAUSTED["gemini-3.8-flash"] - gc.time.monotonic() <= gc.OVERLOADED_SECONDS
