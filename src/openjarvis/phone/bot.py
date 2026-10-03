"""The voice bot that runs a phone call (Pipecat pipeline over Twilio).

Audio flow: Twilio media stream → Silero VAD → faster-whisper (speech to
text) → the same model Sergio uses → Kokoro (text to speech) → Twilio.

Rules the bot always follows (also stated in its system prompt):
* It opens every call to a third party by saying it is an AI assistant
  calling on behalf of the owner.
* It shares only what the goal requires and never invents facts.
* It hangs up itself (``end_call``) once the goal is done or impossible.
"""

from __future__ import annotations

import hmac
import logging
import time
from typing import Any

from openjarvis.phone import calls

logger = logging.getLogger(__name__)

_LANG_NAMES = {"es": "español", "en": "English", "pt": "português", "fr": "français"}


def _owner(config: Any) -> str:
    return (config.phone.owner_name or "").strip() or "su usuario"


def greeting(config: Any, record: calls.CallRecord) -> str:
    """First sentence of the call (the AI disclosure for third parties)."""
    from openjarvis.phone.numbers import is_owner

    owner = _owner(config)
    if record.kind == calls.INBOUND_OWNER:
        return f"Hola {owner}, soy Sergio. ¿En qué te ayudo?"
    if is_owner(record.to, config.phone.owner_numbers):
        return f"Hola {owner}, soy Sergio, tu asistente."
    return (
        f"Hola, buenas. Le habla Sergio, un asistente de inteligencia artificial "
        f"que llama de parte de {owner}."
    )


def system_prompt(config: Any, record: calls.CallRecord) -> str:
    lang = _LANG_NAMES.get(config.phone.language, config.phone.language)
    owner = _owner(config)
    common = (
        f"Habla en {lang}. Es una llamada telefónica: usa frases cortas y "
        "naturales, sin listas, emojis ni formato. Nunca inventes datos que no "
        "tengas; si te piden algo que no sabes, dilo y ofrece confirmarlo "
        "después. Cuando la conversación termine, despídete con una frase y "
        "llama a la función end_call con un resumen breve del resultado."
    )
    if record.kind == calls.INBOUND_OWNER:
        return (
            f"Eres Sergio, el asistente personal de {owner}. {owner} te está "
            f"llamando por teléfono. Ayúdale con lo que necesite. {common}"
        )
    return (
        f"Eres Sergio, un asistente de inteligencia artificial que hace una "
        f"llamada en nombre de {owner}. Ya te presentaste como asistente de IA. "
        f"Objetivo de la llamada: {record.goal}\n"
        "Comparte solo la información necesaria para el objetivo (nunca datos "
        f"privados de {owner} que no hagan falta). Si no se puede lograr, "
        f"despídete amablemente. {common}"
    )


def _language(code: str) -> Any:
    from pipecat.transcriptions.language import Language

    try:
        return Language(code)
    except ValueError:
        return Language.ES


def _llm_service(config: Any, prompt: str) -> Any:
    """Pipecat LLM service for the model Sergio is configured with."""
    from openjarvis.unified.model_bridge import clacky_env

    env = clacky_env(config)
    base_url, key, model = (
        env["CLACKY_BASE_URL"],
        env["CLACKY_API_KEY"],
        env["CLACKY_MODEL"],
    )
    if env["CLACKY_ANTHROPIC_FORMAT"] == "true":
        from pipecat.services.anthropic.llm import AnthropicLLMService

        return AnthropicLLMService(
            api_key=key,
            settings=AnthropicLLMService.Settings(
                model=model, system_instruction=prompt
            ),
        )
    if key == "ollama":
        from pipecat.services.ollama.llm import OLLamaLLMService

        return OLLamaLLMService(
            base_url=base_url.rstrip("/"),
            settings=OLLamaLLMService.Settings(model=model, system_instruction=prompt),
        )
    from pipecat.services.openai.llm import OpenAILLMService

    return OpenAILLMService(
        api_key=key,
        base_url=base_url,
        settings=OpenAILLMService.Settings(model=model, system_instruction=prompt),
    )


def transcript_from(messages: list[Any]) -> list[dict[str, str]]:
    """User/assistant turns as plain text (tool calls and system dropped)."""
    turns: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role not in ("user", "assistant") or not content:
            continue
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        text = str(content).strip()
        if text:
            turns.append({"role": "them" if role == "user" else "sergio", "text": text})
    return turns


async def run_call(websocket: Any, config: Any) -> None:
    """Handle one Twilio media-stream websocket until the call ends."""
    from pipecat.runner.utils import parse_telephony_websocket

    _, call_data = await parse_telephony_websocket(websocket)
    body = call_data.get("body", {}) or {}
    record = calls.load(str(body.get("call_id", "")))
    presented = str(body.get("token") or "")
    if (
        record is None
        or not presented
        or not hmac.compare_digest(presented, record.token)
    ):
        logger.warning("Rejected phone websocket with an unknown call/token")
        await websocket.close()
        return
    if record.status != calls.QUEUED:
        logger.warning("Rejected reuse of call %s", record.id)
        await websocket.close()
        return
    calls.update(record.id, status=calls.IN_PROGRESS)
    try:
        await _run_pipeline(websocket, config, record, call_data)
    except Exception as exc:  # noqa: BLE001 — setup or audio failure: record it
        logger.exception("Call %s failed", record.id)
        calls.update(
            record.id, status=calls.FAILED, error=str(exc), ended_at=time.time()
        )


async def _run_pipeline(
    websocket: Any, config: Any, record: calls.CallRecord, call_data: Any
) -> None:
    """Build the voice pipeline and run it until the call ends."""
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import EndFrame, TTSSpeakFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.serializers.twilio import TwilioFrameSerializer
    from pipecat.services.kokoro.tts import KokoroTTSService
    from pipecat.services.whisper.stt import WhisperSTTService
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )
    from pipecat.workers.runner import WorkerRunner

    sid, token, _ = calls.credentials()
    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data.get("call_id"),
        account_sid=sid,
        auth_token=token,
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )
    language = _language(config.phone.language)
    stt = WhisperSTTService(
        settings=WhisperSTTService.Settings(
            model=config.phone.stt_model, language=language
        )
    )
    tts = KokoroTTSService(
        settings=KokoroTTSService.Settings(
            voice=config.phone.tts_voice, language=language
        )
    )
    llm = _llm_service(config, system_prompt(config, record))

    summary: dict[str, str] = {}
    end_call = FunctionSchema(
        name="end_call",
        description="Hang up after saying goodbye. Call it when the call is over.",
        properties={
            "summary": {"type": "string", "description": "Result of the call."}
        },
        required=["summary"],
    )
    context = LLMContext(tools=ToolsSchema(standard_tools=[end_call]))
    aggregators = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            aggregators.assistant(),
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000),
        idle_timeout_secs=60,
    )

    async def _end_call(params: Any) -> None:
        summary["text"] = str((params.arguments or {}).get("summary", ""))
        await params.result_callback({"ok": True})
        await task.queue_frame(EndFrame())  # graceful: finishes the goodbye

    llm.register_function("end_call", _end_call)

    @transport.event_handler("on_client_connected")
    async def _connected(_transport: Any, _client: Any) -> None:
        await task.queue_frames([TTSSpeakFrame(greeting(config, record))])

    @transport.event_handler("on_client_disconnected")
    async def _disconnected(_transport: Any, _client: Any) -> None:
        await task.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(task)
    await runner.run()
    calls.update(
        record.id,
        status=calls.COMPLETED,
        ended_at=time.time(),
        transcript=transcript_from(context.get_messages()),
        summary=summary.get("text", ""),
    )


__all__ = ["greeting", "run_call", "system_prompt", "transcript_from"]
