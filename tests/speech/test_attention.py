import asyncio
from types import SimpleNamespace as NS

from openjarvis.speech.attention import Attention


def test_room_conversation_and_followups():
    now = [0.0]
    attention = Attention(clock=lambda: now[0])
    assert attention.accepts("¿Qué ves en la pantalla?")
    assert not attention.accepts("No te hablo, estoy hablando por teléfono")
    assert not attention.accepts("pásame eso")
    assert attention.accepts("Sergio, ahora sí, ayúdame")
    assert attention.accepts("¿Y cómo lo arreglo?")
    assert not attention.accepts("Sergio dijo que era azul")
    now[0] = 200
    assert not attention.accepts("abre esto")
    assert attention.accepts("Sergio, abre esto")


def test_a_speaker_change_is_not_an_authorized_request():
    attention = Attention()
    attention.speaker(owner=False)
    assert not attention.accepts("abre mi correo")
    assert attention.accepts("Sergio, ¿qué hora es?")
    attention.speaker(owner=True)
    assert not attention.accepts("hablaba contigo, mamá")
    assert attention.accepts("Sergio, explícame esto")


def test_live_does_not_play_or_act_on_explicit_side_conversation():
    from openjarvis.speech.gemini_live import LiveCall
    from tests.server.test_live_routes import FakeSession, FakeTypes, FakeWS

    async def run():
        ws = FakeWS()
        invoked = []
        call = LiveCall(
            ws,
            {"attention": "addressed"},
            types=FakeTypes(),
            execute=lambda *args: invoked.append(args),
        )
        await call._content(
            NS(
                input_transcription=NS(text="No te hablo"),
                model_turn=NS(parts=[NS(inline_data=NS(data=b"sound"))]),
                output_transcription=NS(text="Lo abro"),
            )
        )
        session = FakeSession([])
        await call._run_tool(
            session, NS(name="desktop_action", args={"action": "click"}, id="x")
        )
        assert ws.audio == [] and invoked == []
        assert any(e["type"] == "interrupted" for e in ws.json)
        assert not any(e["type"] == "said" for e in ws.json)
        assert (
            "No se ejecutó"
            in session.sent[0][1]["function_responses"][0].response["result"]
        )

    asyncio.run(run())


def test_a_video_playing_is_not_for_him():
    from openjarvis.speech.attention import looks_like_media

    now = [0.0]
    attention = Attention(clock=lambda: now[0])
    assert not attention.accepts(
        "hola a todos, bienvenidos a mi canal, hoy vamos a ver"
    )
    assert not attention.accepts("¿y qué opinas?")  # the video closed the window
    assert attention.accepts("Sergio, ¿qué hora es?")
    assert not attention.accepts("so what you know is that this is really the best")
    assert looks_like_media("palabra " * 50)
    assert not looks_like_media("abre la calculadora por favor")


def test_the_follow_up_window_is_short_and_renewed_by_his_answers():
    now = [0.0]
    attention = Attention(clock=lambda: now[0])
    assert attention.accepts("Sergio, pon música")
    now[0] = 25
    attention.answered()
    now[0] = 50
    assert attention.accepts("súbele el volumen")  # 25 s after his answer
    now[0] = 200
    assert not attention.accepts("bájale")


def test_live_holds_an_uncertain_answer_and_drops_speech_to_nobody():
    from openjarvis.speech.gemini_live import HOLD_BYTES, LiveCall
    from tests.server.test_live_routes import FakeTypes, FakeWS

    async def run():
        ws = FakeWS()
        call = LiveCall(ws, {"attention": "addressed"}, types=FakeTypes())
        # Audio before the transcript: held, then released when it is for him.
        await call._content(NS(model_turn=NS(parts=[NS(inline_data=NS(data=b"aa"))])))
        assert ws.audio == []
        await call._content(NS(input_transcription=NS(text="Sergio, ¿qué hora es?")))
        assert ws.audio == [b"aa"]
        await call._content(NS(turn_complete=True))
        # Speaking by himself afterwards (nobody asked): dropped.
        await call._content(
            NS(model_turn=NS(parts=[NS(inline_data=NS(data=b"x" * (HOLD_BYTES + 2)))]))
        )
        await call._content(NS(turn_complete=True))
        assert ws.audio == [b"aa"]

    asyncio.run(run())


def test_talking_about_music_is_not_a_video():
    from openjarvis.speech.attention import looks_like_media

    assert not looks_like_media("súbele a la música")
    assert looks_like_media("[Música] y ahora vamos")
