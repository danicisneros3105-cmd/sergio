"""The chat answer is streamed as it is written (agents/_stubs.stream_tokens)."""

import threading
import time

from openjarvis.agents.orchestrator import OrchestratorAgent
from openjarvis.engine._stubs import InferenceEngine, StreamChunk
from openjarvis.server.models import ChatCompletionRequest, ChatMessage
from openjarvis.server.routes import _handle_agent


class _Engine(InferenceEngine):
    engine_id = "fake"

    def __init__(self, chunks=None, fail=False, delay=0.0):
        self.chunks = chunks or [StreamChunk(content="Ho"), StreamChunk(content="la")]
        self.fail = fail
        self.delay = delay
        self.generated = 0

    def generate(self, messages, *, model, temperature=0.7, max_tokens=1024, **kw):
        self.generated += 1
        time.sleep(self.delay)
        return {"content": "entero", "usage": {}}

    async def stream(self, messages, **kw):
        yield ""

    async def stream_full(self, messages, **kw):
        if self.fail:
            raise RuntimeError("no stream")
        for chunk in self.chunks:
            yield chunk

    def list_models(self):
        return []

    def health(self):
        return True


def _agent(engine):
    return OrchestratorAgent(engine=engine, model="m", tools=[])


def _req(text="hola"):
    return ChatCompletionRequest(
        model="m", messages=[ChatMessage(role="user", content=text)]
    )


def test_words_reach_the_sink_as_they_come():
    got = []
    resp = _handle_agent(_agent(_Engine()), "m", _req(), sink=got.append)
    assert got == ["Ho", "la"]
    assert resp.choices[0].message.content == "Hola"


def test_without_a_sink_nothing_changes():
    engine = _Engine()
    resp = _handle_agent(_agent(engine), "m", _req())
    assert resp.choices[0].message.content == "entero"
    assert engine.generated == 1


def test_an_engine_that_cannot_stream_answers_at_once():
    engine = _Engine(fail=True)
    got = []
    resp = _handle_agent(_agent(engine), "m", _req(), sink=got.append)
    assert got == [] and resp.choices[0].message.content == "entero"


def test_streamed_tool_calls_are_put_back_together():
    from openjarvis.agents._stubs import _merge_tool_calls

    calls: dict = {}
    _merge_tool_calls(
        calls,
        [{"index": 0, "id": "c1", "function": {"name": "calc", "arguments": '{"a"'}}],
    )
    _merge_tool_calls(calls, [{"index": 0, "function": {"arguments": ": 1}"}}])
    assert calls[0] == {"id": "c1", "name": "calc", "arguments": '{"a": 1}'}


def test_two_requests_run_at_the_same_time():
    """A voice turn no longer waits for a chat turn on the same agent."""
    agent = _agent(_Engine(delay=0.4))
    t0 = time.monotonic()
    threads = [
        threading.Thread(target=_handle_agent, args=(agent, "m", _req()))
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert time.monotonic() - t0 < 0.75
    assert agent._model == "m"
