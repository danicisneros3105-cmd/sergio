"""The owner's Pinterest boards, through the official API, measured on his computer.

The owner (3 Nov 2026): «conéctate a mi cuenta de Pinterest … analiza miles de
imágenes de mis tableros». Done the honest way:

* Only the official API v5 with **his** access token (``PINTEREST_TOKEN`` in
  ``~/.openjarvis/sergio.env``; scopes ``boards:read`` and ``pins:read``, made
  in his Pinterest developer app). No scraping, no other accounts: Sergio never
  disguises itself or slips past a site's limits.
* Pictures are downloaded **to his computer only** (``~/.openjarvis/estetica/
  pinterest``) to be measured for his own use; nothing is published or shared.
* The home feed is not part of the public API: boards and their sections are.

The result is ``perfil.json``: for each measure, the percentiles 10/50/90 of his
references, overall and per board, which the superskills' matrices use as ranges.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

API = "https://api.pinterest.com/v5"
MEASURES = ("espacio_negativo", "aureo_dist", "tercios_dist", "brillo", "contraste", "sombras", "negro", "luces",
            "escalones", "saturacion_media", "tonos", "dispersion_tono", "calidez", "simetria")  # fmt: skip


class PinterestError(RuntimeError):
    pass


def home() -> Path:
    from openjarvis.core.config import get_config_dir

    path = Path(get_config_dir()) / "estetica"
    path.mkdir(parents=True, exist_ok=True)
    return path


def token() -> str:
    tok = os.environ.get("PINTEREST_TOKEN", "").strip()
    if not tok:
        raise PinterestError(
            "Falta PINTEREST_TOKEN en ~/.openjarvis/sergio.env: créelo en su app de desarrollador de "
            "Pinterest (developers.pinterest.com) con permisos boards:read y pins:read."
        )
    return tok


def _get(path: str, params: Dict[str, Any], http: Any) -> Dict[str, Any]:
    for attempt in range(5):
        r = http.get(
            f"{API}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token()}"},
            timeout=30,
        )
        if r.status_code == 429:  # their rate limit: wait as they ask
            time.sleep(min(60, int(r.headers.get("Retry-After", 2**attempt))))
            continue
        if r.status_code == 401:
            raise PinterestError(
                "Pinterest no acepta el token (caducado o sin permisos)."
            )
        r.raise_for_status()
        return r.json()
    raise PinterestError(
        "Pinterest pidió esperar demasiadas veces; inténtelo más tarde."
    )


def _pages(path: str, http: Any, page_size: int = 100) -> Iterator[Dict[str, Any]]:
    bookmark = None
    while True:
        params: Dict[str, Any] = {"page_size": page_size}
        if bookmark:
            params["bookmark"] = bookmark
        data = _get(path, params, http)
        yield from data.get("items", [])
        bookmark = data.get("bookmark")
        if not bookmark:
            return


def _image_url(pin: Dict[str, Any]) -> str:
    imgs = (pin.get("media") or {}).get("images") or {}
    for size in ("1200x", "600x", "originals", "400x300"):
        if imgs.get(size, {}).get("url"):
            return imgs[size]["url"]
    return ""


def ingest(*, boards: Optional[List[str]] = None, max_images: int = 3000, http: Any = None,
           progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:  # fmt: skip
    """Downloads the pictures of his boards (or the named ones) and measures them."""
    from openjarvis.estetica import medir

    if http is None:
        import httpx

        http = httpx.Client(follow_redirects=True)
    root = home() / "pinterest"
    rows: List[Dict[str, Any]] = []
    wanted = {b.lower() for b in boards or []}
    for board in _pages("/boards", http):
        name = str(board.get("name", ""))
        if wanted and name.lower() not in wanted:
            continue
        folder = root / "".join(c if c.isalnum() else "-" for c in name)[:60]
        folder.mkdir(parents=True, exist_ok=True)
        for pin in _pages(f"/boards/{board['id']}/pins", http):
            if len(rows) >= max_images:
                break
            url = _image_url(pin)
            if not url:
                continue
            dest = folder / f"{pin['id']}.jpg"
            try:
                if not dest.exists():
                    r = http.get(url, timeout=30)
                    r.raise_for_status()
                    dest.write_bytes(r.content)
                m = medir.measure(dest)
            except Exception:  # noqa: BLE001 — one bad picture is skipped
                continue
            rows.append(
                {
                    "tablero": name,
                    "pin": pin["id"],
                    "titulo": pin.get("title") or "",
                    **m,
                }
            )
            if progress and len(rows) % 50 == 0:
                progress(f"{len(rows)} imágenes medidas")
        if len(rows) >= max_images:
            break
    (home() / "medidas.json").write_text(json.dumps(rows, ensure_ascii=False), "utf-8")
    prof = profile(rows)
    (home() / "perfil.json").write_text(
        json.dumps(prof, ensure_ascii=False, indent=1), "utf-8"
    )
    return {
        "imagenes": len(rows),
        "tableros": sorted({r["tablero"] for r in rows}),
        "perfil": str(home() / "perfil.json"),
    }


def _pct(values: List[float]) -> Dict[str, float]:
    v = sorted(values)
    if not v:
        return {}
    q = statistics.quantiles(v, n=10) if len(v) >= 2 else [v[0]] * 9
    return {
        "p10": round(q[0], 3),
        "p50": round(statistics.median(v), 3),
        "p90": round(q[-1], 3),
    }


def profile(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Percentiles of every measure, overall and per board."""

    def of(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            k: _pct([float(r[k]) for r in rs if isinstance(r.get(k), (int, float))])
            for k in MEASURES
        }

    boards: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        boards.setdefault(r["tablero"], []).append(r)
    return {"imagenes": len(rows), "general": of(rows), "tableros": {b: {"imagenes": len(rs), **of(rs)}
                                                                     for b, rs in boards.items()}}  # fmt: skip


def owner_ranges(path: Optional[Path] = None) -> Optional[Dict[str, Dict[str, tuple]]]:
    """The matrices' measurable ranges taken from his references (p10-p90)."""
    from openjarvis.estetica.medir import DEFAULT_RANGES

    try:
        prof = json.loads((path or home() / "perfil.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    gen = prof.get("general") or {}
    out: Dict[str, Dict[str, tuple]] = {}
    for key, rules in DEFAULT_RANGES.items():
        out[key] = {}
        for name, rng in rules.items():
            p = gen.get(name) or {}
            out[key][name] = (p["p10"], p["p90"]) if "p10" in p and "p90" in p else rng
    return out


__all__ = ["PinterestError", "ingest", "owner_ranges", "profile", "token"]
