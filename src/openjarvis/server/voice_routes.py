"""Sergio's Gemini voice and ears for the Windows companion.

* ``POST /v1/voice/speak`` {text, voice} -> audio/wav
* ``POST /v1/voice/transcribe`` (multipart "file": WAV) -> {"text": ...}
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/v1/voice", tags=["voice"])
MAX_AUDIO = 8 * 1024 * 1024


def preferred(voice: str) -> str:
    """Resolve only the default; never replace an explicitly chosen voice."""
    import os

    if (
        voice.lower() in ("", "default", "predeterminada")
        and os.environ.get("ELEVENLABS_API_KEY", "").strip()
    ):
        configured = os.environ.get("SERGIO_VOICE", "").strip()
        if configured.lower().startswith("elevenlabs"):
            return configured if ":" in configured else "elevenlabs:"
    from openjarvis.speech.gemini_voice import DEFAULT_VOICE, VOICES

    if voice.lower() in ("", "default", "predeterminada"):
        return DEFAULT_VOICE
    if voice.lower() == "elevenlabs":
        return "elevenlabs:"
    name = voice.split(":", 1)[-1] if voice.lower().startswith("gemini:") else voice
    return next((v for v in VOICES if v.lower() == name.lower()), name)


class SpeakRequest(BaseModel):
    text: str
    voice: str = ""
    # ISO 639-1 ("es", "en", "fr"…); empty = worked out from the text.
    language: str = ""
    # The sentence spoken just before, so the intonation flows on (and the
    # language of a sentence too short to tell, like «OK»).
    previous: str = ""
    # The app's language, the last resort for a short first sentence.
    hint: str = ""


@router.post("/speak")
async def speak(req: SpeakRequest) -> Response:
    from openjarvis.speech import gemini_voice

    req = req.model_copy(update={"voice": preferred(req.voice)})
    if req.voice.lower().startswith("elevenlabs"):
        from openjarvis.speech import elevenlabs_voice

        try:
            wav = await asyncio.to_thread(
                elevenlabs_voice.speak_wav,
                req.text,
                req.voice,
                language=req.language,
                previous=req.previous,
                hint=req.hint,
            )
            return Response(content=wav, media_type="audio/wav")
        except Exception as exc:  # noqa: BLE001 — preserve the selected identity
            raise HTTPException(
                502, "La voz seleccionada de ElevenLabs no está disponible."
            ) from exc
    if req.voice.lower() in ("", "predeterminada", "default", "algenib"):
        # Gemini Live's voice, the same as in calls.
        from openjarvis.speech.gemini_live import speak_live

        try:
            wav = await asyncio.to_thread(
                speak_live,
                req.text,
                ""
                if req.voice.lower() in ("", "predeterminada", "default")
                else req.voice,
            )
            return Response(content=wav, media_type="audio/wav")
        except Exception as exc:  # noqa: BLE001 — the TTS models next
            live_error = str(exc)
        try:
            wav = await asyncio.to_thread(gemini_voice.speak, req.text, "Algenib")
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(
                status_code=502, detail=f"{live_error} | {exc}"[:500]
            ) from exc
        return Response(content=wav, media_type="audio/wav")
    try:
        wav = await asyncio.to_thread(
            gemini_voice.speak, req.text, req.voice or gemini_voice.DEFAULT_VOICE
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=wav, media_type="audio/wav")


async def _close(gen: Any) -> None:
    """Close an audio stream; one still producing (the listener hung up mid
    chunk) is already being torn down, which used to log «aclose(): asynchronous
    generator is already running»."""
    try:
        await gen.aclose()
    except RuntimeError:
        pass


@router.post("/stream")
async def stream(req: SpeakRequest) -> Any:
    """Gemini Live reading the text aloud, streamed as raw PCM (24 kHz, int16)
    so the companion starts playing within a second."""
    from fastapi.responses import StreamingResponse

    from openjarvis.speech.gemini_live import stream_live

    voice = preferred(req.voice)
    voice = "" if voice.lower() in ("", "predeterminada", "default") else voice
    first = b""
    if voice.lower().startswith("elevenlabs"):
        from openjarvis.speech.elevenlabs_voice import stream_pcm

        chunks = stream_pcm(
            req.text,
            voice,
            language=req.language,
            previous=req.previous,
            hint=req.hint,
        )
    else:
        chunks = stream_live(req.text, voice)
    try:
        for _ in range(64):
            first = await asyncio.wait_for(chunks.__anext__(), timeout=30)
            if first:
                break
        if not first:
            raise RuntimeError("La voz seleccionada no devolvió audio.")
    except StopAsyncIteration:
        await _close(chunks)
        raise HTTPException(
            status_code=502, detail="La voz seleccionada no devolvió audio."
        ) from None
    except Exception as exc:  # noqa: BLE001
        await _close(chunks)
        raise HTTPException(502, "La voz seleccionada no está disponible.") from exc

    async def body():
        try:
            yield first
            async for chunk in chunks:
                yield chunk
        finally:
            await _close(chunks)

    return StreamingResponse(body(), media_type="audio/L16;rate=24000")


class ChatRequest(BaseModel):
    model: str
    messages: list[dict[str, str]]
    max_tokens: int = 400
    # A question about facts (prices, news, dates, people, results): the
    # answer is grounded on Google Search instead of the model's memory.
    grounded: bool = False


GROUNDED_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
)


def grounded_answer(
    messages: list[dict[str, str]], max_tokens: int = 600, client: Any = None
) -> dict[str, Any]:
    """Answer with Google Search grounding; returns the text and its sources."""
    import os

    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs

    if client is None:
        from openjarvis.engine.google_client import SwitchingClient

        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("no Gemini key")
        client = SwitchingClient(key)
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    system += (
        "\nAnswer from the search results, not from memory. If the results do not "
        "say it, say you could not confirm it. Keep it spoken and short."
    )
    contents = [
        types.Content(
            role="model" if m.get("role") == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    last: Exception | None = None
    for model in GROUNDED_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.3, max(max_tokens, 1024), "low"),
                    system_instruction=system,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            sources = []
            for cand in resp.candidates or []:
                meta = getattr(cand, "grounding_metadata", None)
                for chunk in getattr(meta, "grounding_chunks", None) or []:
                    web = getattr(chunk, "web", None)
                    if web is not None and getattr(web, "title", None):
                        sources.append(str(web.title))
            text = str(resp.text or "").strip()
            if text and sources:
                return {"content": text, "sources": sources[:5], "grounded": True}
        except Exception as exc:  # noqa: BLE001 — next model
            last = exc
    raise RuntimeError(f"grounded answer failed: {last}")


CHAT_SECONDS = 20.0
CHAT_BACKUP = "gemini-2.5-flash"


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> dict[str, Any]:
    """Fast conversation: straight to the model, no agent and no tools.

    The companion uses it for chatting ("¿cómo estás?", "cuéntame algo"),
    which then answers in about a second instead of running the full agent.
    """
    from openjarvis.connectome.brain import mind_context, remember_exchange
    from openjarvis.core.types import Message, Role

    engine = request.app.state.engine
    roles = {"system": Role.SYSTEM, "user": Role.USER, "assistant": Role.ASSISTANT}
    messages = [
        Message(
            role=roles.get(m.get("role", "user"), Role.USER),
            content=m.get("content", ""),
        )
        for m in req.messages
        if m.get("content")
    ]
    # The spoken talk shares the mind with the chat: the memories that come
    # back ride along, and every answer is remembered (it used to live only in
    # the desktop app's RAM and was gone after a restart).
    heard = next((m.content for m in reversed(messages) if m.role == Role.USER), "")
    recalled = await asyncio.to_thread(mind_context, heard, "voz") if heard else ""
    if recalled:
        messages.insert(0, Message(role=Role.SYSTEM, content=recalled))

    def remember(answer: str) -> None:
        if heard and answer:
            asyncio.get_running_loop().run_in_executor(
                None, remember_exchange, heard, answer, "voz"
            )

    async def run(model: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            engine.generate,
            messages,
            model=model,
            temperature=0.3,
            max_tokens=req.max_tokens,
        )

    if req.grounded:
        try:
            out = await asyncio.wait_for(
                asyncio.to_thread(grounded_answer, req.messages, req.max_tokens),
                timeout=CHAT_SECONDS,
            )
            remember(str(out.get("content") or ""))
            return out
        except Exception:  # noqa: BLE001 — never substitute unverified current facts
            return {
                "content": (
                    "No pude verificar ese dato con fuentes actuales. Puedes pedirme "
                    "que lo investigue con las herramientas disponibles."
                ),
                "sources": [],
                "grounded": False,
            }

    try:
        try:
            # A chat answer is worth seconds: a model that stalls gives way
            # to the backup instead of keeping the user waiting.
            result = await asyncio.wait_for(run(req.model), timeout=CHAT_SECONDS)
        except asyncio.TimeoutError:
            if not str(req.model).startswith("gemini") or req.model.startswith(
                CHAT_BACKUP
            ):
                raise
            result = await asyncio.wait_for(run(CHAT_BACKUP), timeout=CHAT_SECONDS)
    except Exception as exc:  # noqa: BLE001 — the companion falls back
        raise HTTPException(
            status_code=502, detail=str(exc)[:400] or "timeout"
        ) from exc
    answer = str(result.get("content") or "").strip()
    remember(answer)
    return {"content": answer}


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...), language: str = Form("es")
) -> dict[str, Any]:
    from openjarvis.speech import gemini_voice

    data = await file.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise HTTPException(status_code=413, detail="Audio too long")
    try:
        text = await asyncio.to_thread(gemini_voice.transcribe, data, language)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"text": text}


__all__ = ["router"]
