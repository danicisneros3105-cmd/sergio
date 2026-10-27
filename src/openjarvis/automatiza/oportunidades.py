"""Client hunting and job hunting: found, ranked and drafted every day.

The owner (27 Oct 2026): «que también puedan hacer deep research para
automatizar client-hunting para freelance y job-hunting». Every day (or on
demand) Sergio:

1. **finds** — jobs from public boards with open APIs (RemoteOK, Himalayas,
   Arbeitnow, We Work Remotely), and clients by searching the web for people
   and businesses that need what the person offers (Sergio's web search and
   deep research);
2. **ranks** them against the person's profile (skills, languages, place,
   remote, rate) — words in common first, the model's read on top;
3. **drafts** a short, specific proposal or cover letter for the best ones,
   with any model the person has a key for.

Nothing is sent by Sergio: proposals and applications wait as drafts with
their link, and the person sends them (the owner's rule: no automatic
messages; LinkedIn, Upwork and most boards forbid automated applying). The
tracker keeps each one's state (nueva, borrador, enviada, respondió,
descartada) so nothing is drafted twice.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from xml.etree import ElementTree as ET  # noqa: S405 — parsed with safe_xml

UA = {"User-Agent": "Sergio/1.0 (job and client search for its owner)"}
STATES = ("nueva", "borrador", "enviada", "respondio", "descartada")
_LOCK = threading.Lock()


def _dir(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    d = Path(home) / "oportunidades"
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile(home: Optional[Path] = None) -> Dict[str, Any]:
    path = _dir(home) / "perfil.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_profile(data: Dict[str, Any], home: Optional[Path] = None) -> Dict[str, Any]:
    busco = {"empleo": "trabajo"}.get(data.get("busco"), data.get("busco"))
    clean = {
        "busco": busco if busco in ("trabajo", "clientes", "ambos") else "ambos",
        "habilidades": [str(s)[:40] for s in data.get("habilidades") or []][:30],
        "servicio": str(data.get("servicio") or "")[:300],
        "idiomas": [str(s)[:20] for s in data.get("idiomas") or ["español"]][:6],
        "lugar": str(data.get("lugar") or "")[:80],
        "remoto": bool(data.get("remoto", True)),
        "tarifa": str(data.get("tarifa") or "")[:60],
        "sobre_mi": str(data.get("sobre_mi") or "")[:1500],
    }
    (_dir(home) / "perfil.json").write_text(
        json.dumps(clean, ensure_ascii=False, indent=1)
    )
    return clean


def _get(url: str, **kw: Any) -> Any:
    import httpx

    r = httpx.get(url, headers=UA, timeout=30, follow_redirects=True, **kw)
    r.raise_for_status()
    return r


def _id(url: str) -> str:
    return hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


# -- the sources (each returns items, never raises) -----------------------------------------


def remoteok(get: Callable[..., Any] = _get) -> List[Dict[str, Any]]:
    try:
        data = get("https://remoteok.com/api").json()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for j in data if isinstance(data, list) else []:
        if not isinstance(j, dict) or not j.get("url"):
            continue
        out.append({"tipo": "trabajo", "titulo": j.get("position", ""), "empresa": j.get("company", ""),
                    "url": j["url"], "lugar": j.get("location") or "Remoto", "remoto": True,
                    "texto": _text(j.get("description", ""))[:1500], "etiquetas": j.get("tags") or [],
                    "fuente": "RemoteOK"})  # fmt: skip
    return out


def himalayas(get: Callable[..., Any] = _get) -> List[Dict[str, Any]]:
    try:
        data = get("https://himalayas.app/jobs/api", params={"limit": 100}).json()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for j in data.get("jobs") or []:
        url = j.get("applicationLink") or j.get("guid") or ""
        if not url:
            continue
        out.append({"tipo": "trabajo", "titulo": j.get("title", ""), "empresa": j.get("companyName", ""),
                    "url": url, "lugar": ", ".join(j.get("locationRestrictions") or []) or "Remoto",
                    "remoto": True, "texto": _text(j.get("excerpt") or j.get("description", ""))[:1500],
                    "etiquetas": j.get("categories") or [], "fuente": "Himalayas"})  # fmt: skip
    return out


def arbeitnow(get: Callable[..., Any] = _get) -> List[Dict[str, Any]]:
    try:
        data = get("https://www.arbeitnow.com/api/job-board-api").json()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for j in data.get("data") or []:
        if not j.get("url"):
            continue
        out.append({"tipo": "trabajo", "titulo": j.get("title", ""), "empresa": j.get("company_name", ""),
                    "url": j["url"], "lugar": j.get("location", ""), "remoto": bool(j.get("remote")),
                    "texto": _text(j.get("description", ""))[:1500], "etiquetas": j.get("tags") or [],
                    "fuente": "Arbeitnow"})  # fmt: skip
    return out


def weworkremotely(get: Callable[..., Any] = _get) -> List[Dict[str, Any]]:
    try:
        from openjarvis.security.safe_xml import fromstring

        root = fromstring(get("https://weworkremotely.com/remote-jobs.rss").text)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for item in root.iter("item"):
        title, link = item.findtext("title") or "", item.findtext("link") or ""
        if not link:
            continue
        company, _, role = title.partition(":")
        out.append({"tipo": "trabajo", "titulo": (role or title).strip(), "empresa": company.strip() if role else "",
                    "url": link, "lugar": item.findtext("region") or "Remoto", "remoto": True,
                    "texto": _text(item.findtext("description") or "")[:1500], "etiquetas": [],
                    "fuente": "We Work Remotely"})  # fmt: skip
    return out


JOB_SOURCES = {
    "RemoteOK": remoteok,
    "Himalayas": himalayas,
    "Arbeitnow": arbeitnow,
    "WWR": weworkremotely,
}

CLIENT_QUERIES = (
    "{servicio} {lugar} busco freelance",
    "looking for a freelance {skill} {lugar}",
    "hiring {skill} contractor remote",
    "negocios en {lugar} que necesitan {servicio}",
)


def clients(prof: Dict[str, Any], search: Optional[Callable[[str, int], List[Dict[str, str]]]] = None,
            per_query: int = 8) -> List[Dict[str, Any]]:  # fmt: skip
    """People and businesses that need what he offers, from the web."""
    if search is None:
        from openjarvis.research.deep import web_search as search
    skill = (prof.get("habilidades") or [""])[0]
    out: List[Dict[str, Any]] = []
    for q in CLIENT_QUERIES:
        query = " ".join(q.format(servicio=prof.get("servicio") or skill, skill=skill,
                                  lugar=prof.get("lugar") or "").split())  # fmt: skip
        try:
            hits = search(query, per_query)
        except Exception:  # noqa: BLE001
            continue
        for h in hits:
            if h.get("url"):
                out.append({"tipo": "cliente", "titulo": h.get("title", ""), "empresa": "", "url": h["url"],
                            "lugar": prof.get("lugar", ""), "remoto": False, "texto": h.get("snippet", "")[:1500],
                            "etiquetas": [], "fuente": "web", "busqueda": query})  # fmt: skip
    return out


# -- ranking ------------------------------------------------------------------------------------


def _norm(text: str) -> set:
    t = (
        unicodedata.normalize("NFKD", str(text).lower())
        .encode("ascii", "ignore")
        .decode()
    )
    return {w for w in re.findall(r"[a-z0-9+#.]{2,}", t)}


def score(item: Dict[str, Any], prof: Dict[str, Any]) -> float:
    skills = {s.lower() for s in prof.get("habilidades") or []}
    words = _norm(
        " ".join(
            [
                item.get("titulo", ""),
                item.get("texto", ""),
                " ".join(item.get("etiquetas") or []),
            ]
        )
    )
    hit = sum(1 for s in skills if _norm(s) and _norm(s) <= words)
    sc = hit * 3.0
    if prof.get("remoto", True) and item.get("remoto"):
        sc += 1
    if prof.get("lugar") and _norm(prof["lugar"]) & _norm(item.get("lugar", "")):
        sc += 1.5
    if item.get("tipo") == "cliente":
        sc += 0.5 * len(_norm(prof.get("servicio", "")) & words)
    return round(sc, 2)


# -- the tracker ------------------------------------------------------------------------------


def items(home: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = _dir(home) / "lista.json"
    return json.loads(path.read_text()) if path.exists() else []


def _save(rows: List[Dict[str, Any]], home: Optional[Path] = None) -> None:
    (_dir(home) / "lista.json").write_text(json.dumps(rows[-500:], ensure_ascii=False))


def set_state(item_id: str, state: str, home: Optional[Path] = None) -> bool:
    if state not in STATES:
        raise ValueError("estado desconocido")
    with _LOCK:
        rows = items(home)
        for r in rows:
            if r["id"] == item_id:
                r["estado"] = state
                _save(rows, home)
                return True
    return False


DRAFT_PROMPT = """Write, in {language}, a short {what} for this opportunity, from this person. \
Specific to the opportunity (mention one concrete detail of it), honest (only what the profile \
says), 90-140 words, a clear next step, no buzzwords, no emojis.
PERSON: {person}
OPPORTUNITY: {item}
Answer ONLY the text."""


def hunt(
    home: Optional[Path] = None,
    *,
    sources: Optional[Dict[str, Callable[..., List[Dict[str, Any]]]]] = None,
    search: Optional[Callable[[str, int], List[Dict[str, str]]]] = None,
    ask: Optional[Callable[..., str]] = None,
    drafts: int = 8,
) -> Dict[str, Any]:
    """One round: find, rank, draft the best new ones; the tracker grows."""
    prof = profile(home)
    if not prof:
        raise ValueError(
            "Primero cuénteme qué hace y qué busca (perfil de oportunidades)."
        )
    found: List[Dict[str, Any]] = []
    if prof.get("busco") in ("trabajo", "ambos"):
        for fn in (sources or JOB_SOURCES).values():
            found += fn()
    if prof.get("busco") in ("clientes", "ambos"):
        found += clients(prof, search)
    with _LOCK:
        rows = items(home)
        known = {r["id"] for r in rows}
        fresh = []
        for it in found:
            iid = _id(it["url"])
            if iid in known:
                continue
            known.add(iid)
            fresh.append({**it, "id": iid, "puntos": score(it, prof), "estado": "nueva",
                          "encontrada": time.time(), "borrador": ""})  # fmt: skip
        fresh.sort(key=lambda r: -r["puntos"])
        fresh = [r for r in fresh if r["puntos"] > 0] or fresh[:20]
        if ask is None:
            from openjarvis.creator.llm import ask as llm_ask

            def ask(p: str, **kw: Any) -> str:
                return llm_ask(p, max_tokens=1200)

        made = 0
        for r in fresh[:drafts]:
            what = (
                "cover letter"
                if r["tipo"] == "trabajo"
                else "first message offering my service"
            )
            try:
                r["borrador"] = ask(DRAFT_PROMPT.format(
                    language=(prof.get("idiomas") or ["español"])[0], what=what,
                    person=json.dumps(prof, ensure_ascii=False)[:2000],
                    item=json.dumps({k: r.get(k, "") for k in ("titulo", "empresa", "lugar", "texto", "url")},
                                    ensure_ascii=False)[:2500],
                )).strip()[:2000]  # fmt: skip
                r["estado"] = "borrador"
                made += 1
            except Exception:  # noqa: BLE001 — listed without a draft
                continue
        rows = fresh + rows
        _save(rows, home)
    return {
        "nuevas": len(fresh),
        "borradores": made,
        "mejores": [
            {
                k: r[k]
                for k in ("id", "tipo", "titulo", "empresa", "url", "puntos", "estado")
            }
            for r in fresh[:10]
        ],
    }


__all__ = [
    "JOB_SOURCES",
    "STATES",
    "clients",
    "hunt",
    "items",
    "profile",
    "save_profile",
    "score",
    "set_state",
]
_ = ET  # the RSS is parsed by openjarvis.security.safe_xml (no entities)
