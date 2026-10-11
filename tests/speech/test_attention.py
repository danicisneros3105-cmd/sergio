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
        call = LiveCall(ws, {"attention": "addressed"}, types=FakeTypes(),
                        execute=lambda *args: invoked.append(args))
        await call._content(NS(input_transcription=NS(text="No te hablo"),
                               model_turn=NS(parts=[NS(inline_data=NS(data=b"sound"))]),
                               output_transcription=NS(text="Lo abro")))
        session = FakeSession([])
        await call._run_tool(session, NS(name="desktop_action", args={"action": "click"}, id="x"))
        assert ws.audio == [] and invoked == []
        assert any(e["type"] == "interrupted" for e in ws.json)
        assert not any(e["type"] == "said" for e in ws.json)
        assert "No se ejecutó" in session.sent[0][1]["function_responses"].response["result"]
    asyncio.run(run())
