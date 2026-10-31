"""``/v1/meeting/*`` and ``/v1/devices/*``: PRO meeting minutes & multi-device control bridge.

* ``POST /v1/meeting/summarize`` — mixed audio (mic + system/call audio) + timeline + live notes -> minutes, auto-saved to history & proactive reminders.
* ``GET  /v1/meeting/history``   — list saved meeting minutes.
* ``POST /v1/meeting/control``   — start/stop/read meeting recording across PC and/or phone.
* ``POST /v1/devices/heartbeat`` — register phone/PC/tablet client & pull queued multi-device commands.
* ``POST /v1/devices/command``   — dispatch remote command (e.g., start recording video on phone from PC).
* ``POST /v1/devices/upload``    — upload captured phone video/photo/audio back to PC storage.
* ``GET  /v1/devices``           — list connected devices and command log.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from openjarvis.core.paths import get_config_dir

router = APIRouter(tags=["meeting"])

MAX_AUDIO = 200 * 1024 * 1024  # ~20 hours of OGG: plenty
_LOCK = threading.RLock()

# In-memory + persisted multi-device registry and command queue
_DEVICES: Dict[str, Dict[str, Any]] = {}
_DEVICE_QUEUE: List[Dict[str, Any]] = []


def _meetings_path() -> Path:
    d = get_config_dir() / "meetings"
    d.mkdir(parents=True, exist_ok=True)
    return d / "history.json"


def load_meetings_history() -> List[Dict[str, Any]]:
    p = _meetings_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_meeting_record(record: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        items = load_meetings_history()
        record.setdefault("id", f"meet-{int(time.time())}-{uuid.uuid4().hex[:6]}")
        record.setdefault("created_at", time.time())
        items.insert(0, record)
        items = items[:100]
        try:
            _meetings_path().write_text(
                json.dumps(items, ensure_ascii=False, indent=2), "utf-8"
            )
        except OSError:
            pass
        # Also write Markdown file to ~/Documents/Sergio/Reuniones
        try:
            folder = Path.home() / "Documents" / "Sergio" / "Reuniones"
            folder.mkdir(parents=True, exist_ok=True)
            safe = (
                re.sub(
                    r"[^\w áéíóúñÁÉÍÓÚÑ-]",
                    "",
                    str(record.get("titulo") or "Reunión"),
                )[:60].strip()
                or "Reunión"
            )
            stamp = time.strftime("%Y-%m-%d_%H%M")
            md_path = folder / f"{stamp}_{safe}.md"
            md_path.write_text(str(record.get("markdown") or ""), "utf-8")
            record["saved_path"] = str(md_path)
        except OSError:
            pass
    return record


def _schedule_meeting_task_reminders(minutes: Dict[str, Any]) -> List[str]:
    """Automatically schedule proactive reminders for tasks decided in a meeting."""
    scheduled: List[str] = []
    tasks = minutes.get("tareas") or []
    if not tasks:
        return scheduled
    from openjarvis.tools.commerce_intel import schedule_proactive_reminder

    for idx, t in enumerate(tasks[:8]):
        if not isinstance(t, dict):
            continue
        what = str(t.get("que") or "").strip()
        who = str(t.get("quien") or "").strip()
        when = str(t.get("cuando") or "").strip()
        if not what:
            continue
        label = f"[Acta: {minutes.get('titulo', 'Reunión')}] {who + ': ' if who else ''}{what}" + (
            f" ({when})" if when else ""
        )
        schedule_proactive_reminder(
            label,
            when_hint=when or f"En {4 + idx} horas",
            category="reunion",
            hours_from_now=float(4 + idx),
        )
        scheduled.append(label)
    return scheduled


@router.post("/v1/meeting/summarize")
async def summarize(
    audio: UploadFile = File(...),
    timeline: str = Form(""),
    kind: str = Form("reunión"),
    when: str = Form(""),
    seconds: float = Form(0.0),
    speakers: str = Form(""),
    live_notes: str = Form(""),
    auto_remind: bool = Form(True),
) -> dict[str, Any]:
    from openjarvis.faces.routes import owner_name
    from openjarvis.tools.meeting_notes import by_person, to_markdown
    from openjarvis.tools.meeting_notes import summarize as write_minutes

    data = await audio.read(MAX_AUDIO + 1)
    if not data or len(data) > MAX_AUDIO:
        raise HTTPException(status_code=413, detail="Audio vacío o demasiado grande")
    mime = audio.content_type or "audio/ogg"
    try:
        names = (
            [s for s in json.loads(speakers) if isinstance(s, str)] if speakers else []
        )
    except ValueError:
        names = []
    full_timeline = timeline
    if live_notes.strip():
        full_timeline = (
            (timeline + "\n" if timeline else "")
            + f"Notas y marcadores en vivo tomados durante la {kind}:\n{live_notes.strip()}"
        )
    try:
        minutes = await asyncio.to_thread(
            write_minutes, data, mime, full_timeline, owner=owner_name(), kind=kind
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result = {
        **minutes,
        "kind": kind,
        "when": when or time.strftime("%d/%m/%Y %H:%M"),
        "seconds": seconds,
        "personas": by_person(minutes),
        "markdown": to_markdown(minutes, when=when, seconds=seconds, speakers=names),
    }
    if auto_remind:
        result["recordatorios_creados"] = _schedule_meeting_task_reminders(result)
    save_meeting_record(result)
    return result


@router.get("/v1/meeting/history")
async def meeting_history(limit: int = 25) -> dict[str, Any]:
    items = load_meetings_history()[: max(1, min(limit, 100))]
    return {"meetings": items, "count": len(items)}


class MeetingControlRequest(BaseModel):
    action: str = Field(default="start", description="start | stop | last")
    kind: str = Field(default="reunión", description="reunión | llamada | conversación")
    device: str = Field(default="both", description="pc | phone | both")


@router.post("/v1/meeting/control")
async def meeting_control(req: MeetingControlRequest) -> dict[str, Any]:
    act = req.action.strip().lower()
    results: List[str] = []
    if req.device in ("pc", "both"):
        try:
            from openjarvis.server.desktop_routes import _skill

            skill_name = (
                "meeting_start"
                if act in ("start", "empezar", "grabar")
                else "meeting_stop"
            )
            res = await asyncio.to_thread(_skill, skill_name, {"kind": req.kind})
            if res:
                results.append(f"PC: {res}")
        except Exception:  # noqa: BLE001
            pass
    if req.device in ("phone", "both"):
        cmd = dispatch_device_command(
            target_device="phone",
            action="record_meeting" if act in ("start", "empezar", "grabar") else "stop_meeting",
            params={"kind": req.kind},
        )
        results.append(f"Teléfono/Web: orden «{cmd['action']}» enviada ({cmd['id']})")
    if act in ("last", "ultima", "última"):
        hist = load_meetings_history()
        return {"ok": True, "last": hist[0] if hist else None, "results": results}
    return {"ok": True, "action": act, "kind": req.kind, "results": results}


# -- Multi-Device Control Bridge (/v1/devices/*) ------------------------------


class DeviceHeartbeatRequest(BaseModel):
    device_id: str
    kind: str = "phone"  # phone | pc | tablet
    name: str = ""
    capabilities: List[str] = Field(
        default_factory=lambda: [
            "camera_video",
            "camera_photo",
            "audio_record",
            "meeting_record",
            "open_url",
            "ring",
            "notify",
        ]
    )


class DeviceCommandRequest(BaseModel):
    target_device: str = "phone"  # phone | pc | tablet | all
    action: str  # record_video | stop_video | take_photo | record_meeting | stop_meeting | open_url | ring | notify | call
    params: Dict[str, Any] = Field(default_factory=dict)


def _try_adb_or_local_bridge(action: str, params: Dict[str, Any]) -> str:
    """If an Android phone is connected via ADB (USB or Wi-Fi), execute the native intent too."""
    if "PYTEST_CURRENT_TEST" in __import__("os").environ:
        return ""
    try:
        adb_cmds: Dict[str, List[str]] = {
            "record_video": [
                "adb",
                "shell",
                "am",
                "start",
                "-a",
                "android.media.action.VIDEO_CAPTURE",
            ],
            "take_photo": [
                "adb",
                "shell",
                "am",
                "start",
                "-a",
                "android.media.action.STILL_IMAGE_CAMERA",
            ],
            "open_url": [
                "adb",
                "shell",
                "am",
                "start",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                str(params.get("url") or "https://google.com"),
            ],
            "call": [
                "adb",
                "shell",
                "am",
                "start",
                "-a",
                "android.intent.action.CALL",
                "-d",
                f"tel:{params.get('to', '')}",
            ],
        }
        cmd = adb_cmds.get(action)
        if not cmd:
            return ""
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.5)
        if proc.returncode == 0:
            return "Ejecutado también por puente ADB directo en el teléfono."
    except Exception:  # noqa: BLE001
        pass
    return ""


def dispatch_device_command(
    target_device: str,
    action: str,
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Queue a remote command for the target device (phone/pc/tablet) and trigger local bridges."""
    payload = dict(params or {})
    adb_note = ""
    if target_device in ("phone", "telefono", "celular", "movil", "all"):
        adb_note = _try_adb_or_local_bridge(action, payload)
    cmd = {
        "id": f"dcmd-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
        "target_device": target_device.lower(),
        "action": action,
        "params": payload,
        "created_at": time.time(),
        "delivered_to": [],
        "adb_bridge": adb_note,
    }
    with _LOCK:
        _DEVICE_QUEUE.append(cmd)
        # Keep only recent commands (last 10 minutes, max 80)
        cutoff = time.time() - 600
        _DEVICE_QUEUE[:] = [c for c in _DEVICE_QUEUE if c["created_at"] >= cutoff][-80:]
    return cmd


@router.post("/v1/devices/heartbeat")
async def device_heartbeat(req: DeviceHeartbeatRequest) -> dict[str, Any]:
    now = time.time()
    did = req.device_id.strip() or "anon"
    kind = req.kind.strip().lower() or "phone"
    with _LOCK:
        _DEVICES[did] = {
            "device_id": did,
            "kind": kind,
            "name": req.name or ("Teléfono del señor" if kind == "phone" else "PC del señor"),
            "capabilities": req.capabilities,
            "last_seen": now,
        }
        pending = []
        for cmd in _DEVICE_QUEUE:
            if now - cmd["created_at"] > 120:
                continue
            if did in cmd["delivered_to"]:
                continue
            target = cmd["target_device"]
            if target in ("all", did, kind) or (
                target in ("phone", "telefono", "celular", "movil") and kind == "phone"
            ):
                cmd["delivered_to"].append(did)
                pending.append(cmd)
    return {"ok": True, "commands": pending, "active_devices": len(_DEVICES)}


@router.post("/v1/devices/command")
async def device_command(req: DeviceCommandRequest) -> dict[str, Any]:
    cmd = await asyncio.to_thread(
        dispatch_device_command, req.target_device, req.action, req.params
    )
    return {"ok": True, "command": cmd}


@router.get("/v1/devices")
async def list_devices() -> dict[str, Any]:
    now = time.time()
    with _LOCK:
        active = [
            {**d, "online": (now - d["last_seen"]) < 45}
            for d in _DEVICES.values()
        ]
        recent_cmds = list(reversed(_DEVICE_QUEUE[-15:]))
    return {"devices": active, "recent_commands": recent_cmds}


@router.post("/v1/devices/upload")
async def device_upload(
    file: UploadFile = File(...),
    device_id: str = Form("phone"),
    kind: str = Form("video"),
    caption: str = Form(""),
) -> dict[str, Any]:
    raw = await file.read(MAX_AUDIO + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    folder_name = "Videos" if kind == "video" else "Pictures"
    out_dir = Path.home() / folder_name / "Sergio" / "Telefono"
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "captura.webm").suffix or (".webm" if kind == "video" else ".jpg")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"telefono-{kind}-{stamp}{ext}"
    out_path.write_bytes(raw)
    return {
        "ok": True,
        "device_id": device_id,
        "kind": kind,
        "caption": caption,
        "saved_path": str(out_path),
        "size_bytes": len(raw),
    }


__all__ = [
    "dispatch_device_command",
    "load_meetings_history",
    "router",
    "save_meeting_record",
]
