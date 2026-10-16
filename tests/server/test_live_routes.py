"""Real-time calls (/v1/live): the Gemini Live bridge, with a fake Gemini."""

import asyncio
import base64
import json
from types import SimpleNamespace as NS

import pytest

from openjarvis.speech import gemini_live
from openjarvis.speech.gemini_live import LiveCall, declarations


class FakeTypes:
    """Stands in for google.genai.types: every type records its arguments."""

    class _Enum:
        def __getattr__(self, name):
            return name

    EndSensitivity = _Enum()

    def __getattr__(self, name):
        return lambda *a, **kw: NS(kind=name, **kw)


class FakeSession:
    def __init__(self, batches):
        self.batches = list(batches)  # one list of messages per receive()
        self.sent = []

    async def send_realtime_input(self, **kw):
        self.sent.append(("input", kw))

    async def send_tool_response(self, **kw):
        self.sent.append(("tool_response", kw))

    async def send_client_content(self, **kw):
        self.sent.append(("content", kw))

    async def receive(self):
        if not self.batches:
            await asyncio.sleep(3600)  # quiet line
        for msg in self.batches.pop(0):
            if callable(msg):
                msg = await msg()
            yield msg


class FakeClient:
    """client.aio.live.connect(...) -> scripted sessions or errors."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.connects = []
        self.aio = NS(live=NS(connect=self.connect))

    def connect(self, model, config):
        self.connects.append((model, config))
        outcome = self.outcomes.pop(0)
        client = self

        class CM:
            async def __aenter__(self):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            async def __aexit__(self, *exc):
                client.closed = True
                return False

        return CM()


class FakeWS:
    def __init__(self):
        self.inbox = asyncio.Queue()
        self.json = []
        self.audio = []

    async def receive(self):
        return await self.inbox.get()

    async def send_json(self, data):
        self.json.append(data)

    async def send_bytes(self, data):
        self.audio.append(data)

    def put(self, **msg):
        self.inbox.put_nowait(msg)


def _content(**kw):
    base = dict(
        model_turn=None,
        input_transcription=None,
        output_transcription=None,
        interrupted=False,
        turn_complete=False,
    )
    base.update(kw)
    return NS(server_content=NS(**base), tool_call=None)


def _call(ws, client, start=None, execute=None, tools=()):
    start = start or {"type": "start", "voice": "Algieba"}
    return LiveCall(
        ws,
        start,
        execute=execute,
        openai_tools=tools,
        owner="Dani",
        client=client,
        types=FakeTypes(),
    )


@pytest.fixture(autouse=True)
def _fresh_search(monkeypatch):
    monkeypatch.setattr(gemini_live, "_search_refused_at", -1e9)


def test_declarations_offer_companion_tools_and_a_few_server_tools():
    server = [
        {
            "type": "function",
            "function": {"name": n, "description": n, "parameters": {}},
        }
        for n in ("desktop_action", "shell_exec", "web_search", "camara")
    ]
    client = [
        {
            "name": "camara",
            "description": "Abre o cierra la cámara.",
            "parameters": {
                "type": "object",
                "properties": {"accion": {"type": "string", "enum": ["abrir"]}},
                "additionalProperties": False,
            },
        }
    ]
    decls = declarations(server, client)
    names = [d["name"] for d in decls]
    assert names == ["camara", "desktop_action", "web_search"]  # no shell_exec
    assert "additionalProperties" not in json.dumps(decls)  # Gemini-safe schema


def test_instructions_carry_owner_context_and_personality():
    text = gemini_live.live_instructions(
        {"context": "Son las 15:20 en Quito.", "personality": "Humor seco."}, "Dani"
    )
    assert "de Dani" in text and "15:20 en Quito" in text and "Humor seco" in text
    assert "llamada en tiempo real" in text


def test_a_whole_call_voice_transcripts_and_tools():
    async def scenario():
        ws = FakeWS()
        pcm = b"\x01\x02" * 100

        async def after_tools():
            # wait until the companion answered its tool
            for _ in range(200):
                if any(k == "tool_response" for k, _ in session.sent[1:]):
                    break
                await asyncio.sleep(0.01)
            return _content(turn_complete=True)

        session = FakeSession(
            [
                [
                    _content(input_transcription=NS(text="Sergio, abre Spotify")),
                    NS(
                        server_content=None,
                        tool_call=NS(
                            function_calls=[
                                NS(
                                    id="c1",
                                    name="desktop_action",
                                    args={"action": "open_app"},
                                ),
                                NS(id="c2", name="camara", args={"accion": "abrir"}),
                            ]
                        ),
                    ),
                ],
                [
                    _content(
                        model_turn=NS(parts=[NS(inline_data=NS(data=pcm))]),
                        output_transcription=NS(text="Listo, señor."),
                    ),
                    after_tools,
                ],
            ]
        )
        client = FakeClient([session])
        ran = []

        def execute(name, args):
            ran.append((name, args))
            return "opened Spotify | now in front: Spotify"

        start = {
            "type": "start",
            "tools": [{"name": "camara", "description": "Cámara", "parameters": {}}],
        }
        call = _call(ws, client, start=start, execute=execute)
        task = asyncio.ensure_future(call.run())
        ws.put(type="websocket.receive", bytes=b"\0\0" * 1600)
        ws.put(
            type="websocket.receive",
            text=json.dumps(
                {"type": "image", "data": base64.b64encode(b"jpg").decode()}
            ),
        )
        # the companion runs its own tool when asked
        for _ in range(300):
            if any(m.get("type") == "call" for m in ws.json):
                break
            await asyncio.sleep(0.01)
        ask = next(m for m in ws.json if m.get("type") == "call")
        assert ask["name"] == "camara" and ask["args"] == {"accion": "abrir"}
        ws.put(
            type="websocket.receive",
            text=json.dumps(
                {"type": "tool_result", "id": ask["id"], "result": "Cámara abierta."}
            ),
        )
        for _ in range(300):
            if any(m.get("type") == "turn_complete" for m in ws.json):
                break
            await asyncio.sleep(0.01)
        ws.put(type="websocket.receive", text=json.dumps({"type": "end"}))
        await asyncio.wait_for(task, 5)
        return ws, session, client, ran

    ws, session, client, ran = asyncio.run(scenario())
    kinds = [m["type"] for m in ws.json]
    assert kinds[0] == "ready" and ws.json[0]["model"] == "gemini-3.8-live"
    assert {"type": "heard", "text": "Sergio, abre Spotify"} in ws.json
    assert {"type": "said", "text": "Listo, señor."} in ws.json
    assert ws.audio == [b"\x01\x02" * 100]  # his voice reaches the companion
    assert ran == [("desktop_action", {"action": "open_app"})]
    tool_events = [m for m in ws.json if m["type"] == "tool"]
    assert [m["status"] for m in tool_events] == ["running", "done"]
    responses = {
        kw["function_responses"][0].name: kw["function_responses"][0].response
        for k, kw in session.sent
        if k == "tool_response"
    }
    assert responses == {
        "desktop_action": {"result": "opened Spotify | now in front: Spotify"},
        "camara": {"result": "Cámara abierta."},
    }
    inputs = [kw for k, kw in session.sent if k == "input"]
    assert inputs[0]["audio"].mime_type == "audio/pcm;rate=16000"
    assert inputs[1]["video"].data == b"jpg"
    assert getattr(client, "closed", False)  # the Gemini session is closed


def test_falls_back_without_search_then_to_the_next_model(monkeypatch):
    monkeypatch.setenv("SERGIO_LIVE_SEARCH", "1")

    async def scenario():
        ws = FakeWS()
        session = FakeSession([])
        quota = RuntimeError("1011 You exceeded your current quota")
        client = FakeClient([quota, quota, session])
        call = _call(ws, client)
        task = asyncio.ensure_future(call.run())
        for _ in range(200):
            if ws.json:
                break
            await asyncio.sleep(0.01)
        ws.put(type="websocket.disconnect")
        await asyncio.wait_for(task, 5)
        return ws, client

    ws, client = asyncio.run(scenario())
    tried = [
        (m, any(getattr(t, "google_search", None) for t in c.tools or []))
        for m, c in client.connects
    ]
    assert tried == [
        ("gemini-3.8-live", True),
        ("gemini-3.8-live", False),
        ("gemini-3.1-flash-live-preview", False),
    ]
    assert ws.json[0] == {
        "type": "ready",
        "model": "gemini-3.1-flash-live-preview",
        "capture_target_fps": 32.310520139305,
        "video_send_fps": 1.0,
    }
    # Search was refused: the next call does not even try it.
    assert gemini_live._search_refused_at > 0


def test_resumes_when_google_rotates_the_connection():
    async def scenario():
        ws = FakeWS()
        first = FakeSession(
            [
                [
                    NS(
                        server_content=None,
                        tool_call=None,
                        session_resumption_update=NS(new_handle="h-123"),
                        go_away=None,
                    ),
                    NS(server_content=None, tool_call=None, go_away=NS(time_left="5s")),
                ]
            ]
        )
        second = FakeSession([])
        client = FakeClient([first, second])
        call = _call(ws, client)
        task = asyncio.ensure_future(call.run())
        for _ in range(300):
            if len(client.connects) >= 2 and not client.outcomes:
                break
            await asyncio.sleep(0.01)
        ws.put(type="websocket.receive", text=json.dumps({"type": "end"}))
        await asyncio.wait_for(task, 5)
        return ws, client

    ws, client = asyncio.run(scenario())
    handles = [c.session_resumption.handle for _m, c in client.connects]
    assert handles[0] is None and handles[-1] == "h-123"
    assert [m["type"] for m in ws.json].count("ready") == 1  # one call for the user


def test_no_model_answers_is_an_error():
    async def scenario():
        ws = FakeWS()
        client = FakeClient([RuntimeError("nope")] * 8)
        call = _call(ws, client)
        with pytest.raises(RuntimeError, match="No pude abrir"):
            await call.run()

    asyncio.run(scenario())


def test_route_needs_start_and_reports_errors(monkeypatch):
    from fastapi.testclient import TestClient

    from openjarvis.server.app import create_app

    class Engine:
        engine_id = "fake"

        def health(self):
            return True

        def list_models(self):
            return ["gemini-3.8-flash"]

    from openjarvis.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    app = create_app(Engine(), "gemini-3.8-flash", config=cfg)
    client = TestClient(app)
    assert client.get("/v1/live/status").status_code == 200

    async def boom(self):
        raise RuntimeError("Falta GEMINI_API_KEY")

    monkeypatch.setattr(LiveCall, "run", boom)
    with client.websocket_connect("/v1/live") as ws:
        ws.send_text(json.dumps({"type": "start"}))
        assert ws.receive_json() == {"type": "error", "message": "Falta GEMINI_API_KEY"}
    with client.websocket_connect("/v1/live") as ws:
        ws.send_text(json.dumps({"type": "hola"}))
        assert ws.receive_json()["type"] == "error"


def test_search_is_off_unless_asked(monkeypatch):
    monkeypatch.delenv("SERGIO_LIVE_SEARCH", raising=False)

    async def scenario():
        ws = FakeWS()
        client = FakeClient([FakeSession([])])
        task = asyncio.ensure_future(_call(ws, client).run())
        for _ in range(200):
            if ws.json:
                break
            await asyncio.sleep(0.01)
        ws.put(type="websocket.disconnect")
        await asyncio.wait_for(task, 5)
        return client

    client = asyncio.run(scenario())
    ((_model, config),) = client.connects
    assert not any(getattr(t, "google_search", None) for t in config.tools or [])


def test_a_dropped_call_reconnects_on_its_own_model_without_an_error():
    """Google drops Live calls ("1011 internal error"). The resume used to be
    tried on the next model too ("1008 session history not found") and the
    call ended with an error the user saw. Now: same model, afresh if
    needed, and the user only notices a short pause."""

    async def boom():
        raise RuntimeError("1011 None. Internal error encountered.")

    async def scenario():
        ws = FakeWS()
        first = FakeSession(
            [
                [
                    NS(
                        server_content=None,
                        tool_call=None,
                        session_resumption_update=NS(new_handle="h-1"),
                        go_away=None,
                    ),
                    boom,
                ]
            ]
        )
        fresh = FakeSession([])
        client = FakeClient(
            [first, RuntimeError("1011 None. Internal error encountered."), fresh]
        )
        call = _call(ws, client)
        task = asyncio.ensure_future(call.run())
        for _ in range(300):
            if len(client.connects) >= 3:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        ws.put(type="websocket.receive", text=json.dumps({"type": "end"}))
        await asyncio.wait_for(task, 5)
        return ws, client

    ws, client = asyncio.run(scenario())
    models = [m for m, _c in client.connects]
    handles = [c.session_resumption.handle for _m, c in client.connects]
    assert models == [gemini_live.LIVE_MODELS[0]] * 3
    assert handles == [None, "h-1", None]
    assert not [m for m in ws.json if m["type"] == "error"]


def test_no_voice_means_gemini_lives_default_voice():
    cfg = gemini_live.live_config(
        FakeTypes(), voice="", instructions="x", decls=[], search=False
    )
    assert cfg.speech_config is None
    cfg = gemini_live.live_config(
        FakeTypes(), voice="Charon", instructions="x", decls=[], search=False
    )
    assert cfg.speech_config is not None


def test_the_shared_screen_is_watched_at_a_legible_resolution(monkeypatch):
    types = pytest.importorskip("google.genai.types")
    cfg = gemini_live.live_config(
        types, voice="", instructions="x", decls=[], search=False
    )
    assert cfg.media_resolution == types.MediaResolution.MEDIA_RESOLUTION_MEDIUM
    monkeypatch.setenv("SERGIO_LIVE_RESOLUTION", "high")
    cfg = gemini_live.live_config(
        types, voice="", instructions="x", decls=[], search=False
    )
    assert cfg.media_resolution == types.MediaResolution.MEDIA_RESOLUTION_HIGH
    assert "video continuo" in gemini_live.INSTRUCTIONS


def test_live_video_preserves_fractional_target():
    assert gemini_live.LIVE_FPS == 32.310520139305
    assert gemini_live.FRAME_GAP < 1 / 32
    assert gemini_live.PROVIDER_VIDEO_FPS == 1


def test_live_config_uses_supported_low_latency_settings_in_real_sdk():
    types = pytest.importorskip("google.genai.types")
    for model in ("gemini-3.8-live", "gemini-3.1-flash-live-preview"):
        cfg = gemini_live.live_config(
            types, voice="", instructions="x", decls=[], search=False, model=model
        )
        vad = cfg.realtime_input_config.automatic_activity_detection
        assert vad.silence_duration_ms == 250
        assert vad.prefix_padding_ms == 300  # keep the beginning of words
        if model == "gemini-3.8-live":
            assert cfg.thinking_config is None
        else:
            assert cfg.thinking_config.thinking_level.value.lower() == "minimal"


def test_latency_is_measured_once_after_input_end_and_not_after_interruption():
    async def scenario():
        ws = FakeWS()
        session = FakeSession([])
        call = _call(ws, FakeClient([]))
        pump = asyncio.create_task(call._pump_up(session))
        ws.put(type="websocket.receive", text=json.dumps({"type": "audio_end"}))
        await asyncio.sleep(0.02)
        audio = _content(
            model_turn=NS(parts=[NS(inline_data=NS(data=b"voice"))])
        ).server_content
        await call._content(audio)
        await call._content(audio)
        await call._content(_content(interrupted=True).server_content)
        await call._content(audio)
        ws.put(type="websocket.disconnect")
        await pump
        return ws

    ws = asyncio.run(scenario())
    reports = [event for event in ws.json if event["type"] == "latency"]
    assert len(reports) == 1
    assert 10 <= reports[0]["server_end_to_first_audio_ms"] < 500
    assert reports[0]["end_to_end_verified"] is False
    assert ws.audio == [b"voice"] * 3


def test_video_metrics_do_not_claim_provider_acknowledgments():
    async def scenario():
        ws = FakeWS()
        call = _call(ws, FakeClient([]))
        now = gemini_live.time.monotonic()
        call._video_reported = now - 3
        call._video_sent = [now - 0.1, now]
        call._video_dropped = 4
        await call._report_video(now)
        return ws.json[-1]

    report = asyncio.run(scenario())
    assert report["target_fps"] == 32.310520139305
    assert report["provider_fps"] is None and report["provider_verified"] is False
    assert report["dropped_frames"] == 4 and report["slow"] is True


def test_notes_reach_the_model_without_ending_a_turn():
    """«Ahora habla Ana»: context for the model, not a question to answer."""

    async def scenario():
        ws = FakeWS()
        session = FakeSession([])
        call = _call(ws, FakeClient([session]))
        task = asyncio.ensure_future(call.run())
        ws.put(
            type="websocket.receive",
            text=json.dumps({"type": "note", "text": "(Ahora habla Ana)"}),
        )
        for _ in range(200):
            if any(k == "content" for k, _ in session.sent):
                break
            await asyncio.sleep(0.01)
        ws.put(type="websocket.receive", text=json.dumps({"type": "end"}))
        await asyncio.wait_for(task, 5)
        return session

    session = asyncio.run(scenario())
    content = [kw for k, kw in session.sent if k == "content"]
    assert content and content[0]["turn_complete"] is False
    assert content[0]["turns"].parts[0].text == "(Ahora habla Ana)"


def test_proactive_audio_first_and_plain_sessions_when_refused(monkeypatch):
    """Proactive audio (v1alpha) lets Sergio stay quiet when people talk to
    each other; a model that refuses it is used without it, for good."""
    monkeypatch.setattr(gemini_live, "_PROACTIVE_OK", [True])

    async def scenario(alpha_outcome):
        ws = FakeWS()
        session = FakeSession([])
        plain = FakeClient([session])
        call = _call(ws, plain)
        call.proactive = True
        call._alpha = FakeClient([alpha_outcome])
        task = asyncio.ensure_future(call.run())
        for _ in range(200):
            if ws.json:
                break
            await asyncio.sleep(0.01)
        ws.put(type="websocket.receive", text=json.dumps({"type": "end"}))
        await asyncio.wait_for(task, 5)
        return call, plain

    call, plain = asyncio.run(scenario(FakeSession([])))
    config = call._alpha.connects[0][1]
    assert config.proactivity.proactive_audio is True and plain.connects == []
    refused = RuntimeError(
        '1007 Invalid JSON payload received. Unknown name "proactivity"'
    )
    call, plain = asyncio.run(scenario(refused))
    assert gemini_live._PROACTIVE_OK == [False]
    assert len(plain.connects) == 1 and not hasattr(plain.connects[0][1], "proactivity")


def test_video_lane_keeps_the_newest_frame_and_never_holds_the_voice(monkeypatch):
    """32 FPS capture is coalesced to provider samples; audio is not queued."""
    monkeypatch.setattr(gemini_live, "VIDEO_REPORT_EVERY", 0.5)

    class SlowSession(FakeSession):
        audio_received_at = None
        video_times = []

        async def send_realtime_input(self, **kw):
            if "video" in kw:
                await asyncio.sleep(0.08)  # ~12 frames a second at most
                self.video_times.append(gemini_live.time.monotonic())
            if "audio" in kw:
                self.audio_received_at = gemini_live.time.monotonic()
            self.sent.append(("input", kw))

    async def scenario():
        ws = FakeWS()
        session = SlowSession([])
        call = _call(ws, FakeClient([session]))
        task = asyncio.ensure_future(call.run())
        await asyncio.sleep(0.05)
        audio_at = None
        for i in range(48):  # 1.5 s of a 32 FPS video
            frame = json.dumps(
                {"type": "image", "data": base64.b64encode(str(i).encode()).decode()}
            )
            ws.put(type="websocket.receive", text=frame)
            if i == 24:
                ws.put(type="websocket.receive", bytes=b"\0\0" * 160)
                audio_at = asyncio.get_running_loop().time()
            await asyncio.sleep(1 / 32)
        await asyncio.sleep(0.3)
        ws.put(type="websocket.receive", text=json.dumps({"type": "end"}))
        await asyncio.wait_for(task, 5)
        return ws, session, audio_at

    ws, session, audio_at = asyncio.run(scenario())
    videos = [kw for kind, kw in session.sent if "video" in kw]
    audio = [kw for kind, kw in session.sent if "audio" in kw]
    assert audio, "the voice went through"
    assert len(videos) == 2
    assert session.video_times[1] - session.video_times[0] >= 1.0
    assert int(videos[1]["video"].data) >= 30  # newest, not frame 1 from a backlog
    assert session.audio_received_at - audio_at < 0.1
    reports = [m for m in ws.json if m.get("type") == "video"]
    assert reports and reports[-1]["send_limit_fps"] == 1
    assert reports[-1]["coalesced_frames"] > 20
