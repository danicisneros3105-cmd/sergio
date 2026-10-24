"""Goals, medications and reminders (see :mod:`openjarvis.reminders`).

* ``GET    /v1/reminders``              — everything, with each medication's adherence
* ``POST   /v1/reminders``              — add a goal, a medication or a reminder
* ``PUT    /v1/reminders/{id}``         — change it (or pause it with ``active``)
* ``DELETE /v1/reminders/{id}``         — remove it
* ``GET    /v1/reminders/due``          — what should be on screen now (polled by the app)
* ``POST   /v1/reminders/{id}/done``    — taken / done, or skipped, for one time slot
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/reminders", tags=["recordatorios"])


def _store():
    from openjarvis.reminders import get_store

    return get_store()


class NewItem(BaseModel):
    kind: str = Field(..., pattern="^(medicina|meta|recordatorio)$")
    title: str = Field(..., min_length=1, max_length=160)
    detail: str = Field("", max_length=1000)
    times: List[str] = Field(default_factory=list, max_length=12)
    days: List[int] = Field(default_factory=list, max_length=7)
    date: str = Field("", max_length=10)
    extra: Dict[str, Any] = Field(default_factory=dict)


class Change(BaseModel):
    title: Optional[str] = Field(None, max_length=160)
    detail: Optional[str] = Field(None, max_length=1000)
    times: Optional[List[str]] = None
    days: Optional[List[int]] = None
    date: Optional[str] = Field(None, max_length=10)
    active: Optional[bool] = None
    extra: Optional[Dict[str, Any]] = None


class Done(BaseModel):
    slot: str = Field(..., min_length=10, max_length=16)
    status: str = Field("hecho", pattern="^(hecho|saltado)$")


def _view(store: Any, item: Dict[str, Any]) -> Dict[str, Any]:
    if item["kind"] == "medicina":
        return {**item, "adherence": store.adherence(item["id"])}
    return item


@router.get("")
def list_items(kind: str = "") -> Dict[str, Any]:
    store = _store()
    return {
        "items": [_view(store, i) for i in store.items(kind)],
        "upcoming": store.upcoming(hours=24)[:20],
    }


@router.post("")
def add_item(body: NewItem) -> Dict[str, Any]:
    store = _store()
    try:
        item = store.add(
            body.kind,
            body.title,
            detail=body.detail,
            times=body.times,
            days=body.days,
            date=body.date,
            extra={k: v for k, v in body.extra.items() if isinstance(k, str)},
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _view(store, item)


@router.put("/{iid}")
def change_item(iid: str, body: Change) -> Dict[str, Any]:
    store = _store()
    item = store.update(iid, **body.model_dump(exclude_none=True))
    if item is None:
        raise HTTPException(404, "No encuentro ese recordatorio.")
    return _view(store, item)


@router.delete("/{iid}")
def delete_item(iid: str) -> Dict[str, Any]:
    if not _store().delete(iid):
        raise HTTPException(404, "No encuentro ese recordatorio.")
    return {"ok": True}


@router.get("/due")
def due() -> Dict[str, Any]:
    return {"due": _store().due()}


@router.post("/{iid}/done")
def done(iid: str, body: Done) -> Dict[str, Any]:
    if not _store().mark(iid, body.slot, body.status):
        raise HTTPException(404, "No encuentro ese recordatorio.")
    return {"ok": True}


__all__ = ["router"]
