"""Models you can take apart in the chat («despiece»), piece by piece.

The owner (26 Oct 2026): «cuando el usuario pida a Sergio que cree un modelo
3D de un auto ultra detallado… recibirá una página dentro del chat donde
podrá ver todo y verlo pieza por pieza con la skill anatomy».

Three ways in, one viewer (``components/Chat/PartsViewer.tsx``):

* **Sergio draws it** (:func:`create`): Gemini lists every part with its real
  size, position, material and what it does — a car is body panels, doors,
  glass, wheels (tyre, rim, spokes, brake disc, caliper, lug nuts), engine,
  gearbox, suspension, seats, steering… — as shapes the viewer builds
  (boxes with rounded edges, cylinders, lathe profiles…). ``espejo`` and
  ``repetir`` copy a part to the other side or around a circle, so a detailed
  model fits in one answer. Parts are grouped (body, wheels, engine…) and
  each group flies apart in its own direction.
* **A free 3D model from the internet** (:func:`search_cc0`, :func:`download`):
  only CC0 models from Poly Haven — free for anyone, credit kept anyway. Game
  mods and ripped game assets are never used: they belong to their studios.
* **A model already on this computer** (:func:`register_file`): a .glb or
  .gltf (Blender exports these), its meshes become the pieces.

Everything lives in ``~/.openjarvis/creator/despiece/<name>/`` and reaches
the chat as ``/v1/creator/despiece/view/<name>``.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openjarvis.creator.llm import CreatorError

SHAPES = ("caja", "cilindro", "esfera", "toro", "capsula", "cono", "perfil")
MATERIALS = (
    "pintura",
    "metal",
    "cromo",
    "goma",
    "vidrio",
    "plastico",
    "cuero",
    "tela",
    "luz",
    "madera",
)
MAX_PARTS = 900
MAX_CM = 5000.0
POLYHAVEN = "https://api.polyhaven.com"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def root(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    return Path(home) / "creator" / "despiece"


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    out = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return out[:60] or "modelo"


def view(name: str) -> str:
    return f"/v1/creator/despiece/view/{name}"


# -- the parts list -----------------------------------------------------------


def _num(
    value: Any, default: float = 0.0, lo: float = -MAX_CM, hi: float = MAX_CM
) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(x):
        return default
    return max(lo, min(hi, x))


def _vec(
    value: Any,
    n: int = 3,
    default: float = 0.0,
    lo: float = -MAX_CM,
    hi: float = MAX_CM,
) -> List[float]:
    items = list(value) if isinstance(value, (list, tuple)) else []
    return [
        round(_num(items[i] if i < len(items) else default, default, lo, hi), 3)
        for i in range(n)
    ]


def clean(data: Dict[str, Any]) -> Dict[str, Any]:
    """A safe, complete parts list from what a model wrote (raises CreatorError)."""
    if not isinstance(data, dict):
        raise CreatorError("El modelo no vino como una lista de piezas.")
    groups: List[Dict[str, Any]] = []
    seen_groups = set()
    for g in data.get("grupos") or []:
        if not isinstance(g, dict):
            continue
        gid = slug(str(g.get("id") or g.get("nombre") or ""))
        if gid in seen_groups:
            continue
        seen_groups.add(gid)
        groups.append(
            {
                "id": gid,
                "nombre": str(g.get("nombre") or gid)[:60],
                "direccion": _vec(g.get("direccion"), 3, 0.0, -1.0, 1.0),
            }
        )
    parts: List[Dict[str, Any]] = []
    ids: set[str] = set()
    for raw in data.get("piezas") or []:
        if not isinstance(raw, dict):
            continue
        for p in _expand(raw):
            shape = str(p.get("forma") or "caja")
            if shape not in SHAPES:
                shape = "caja"
            pid = slug(str(p.get("id") or p.get("nombre") or "pieza"))
            base, n = pid, 2
            while pid in ids:
                pid = f"{base}-{n}"
                n += 1
            ids.add(pid)
            gid = slug(str(p.get("grupo") or "general"))
            if gid not in seen_groups:
                seen_groups.add(gid)
                groups.append(
                    {
                        "id": gid,
                        "nombre": str(p.get("grupo") or "General")[:60],
                        "direccion": [0.0, 0.0, 0.0],
                    }
                )
            color = str(p.get("color") or "#9a9a9a")
            part = {
                "id": pid,
                "nombre": str(p.get("nombre") or pid)[:80],
                "grupo": gid,
                "forma": shape,
                "medidas": _vec(p.get("medidas"), 3, 1.0, 0.01, MAX_CM),
                "redondeo": round(_num(p.get("redondeo"), 0.0, 0.0, 200.0), 2),
                "posicion": _vec(p.get("posicion")),
                "rotacion": _vec(p.get("rotacion"), 3, 0.0, -360.0, 360.0),
                "color": color if _HEX.match(color) else "#9a9a9a",
                "material": str(p.get("material") or "plastico")
                if p.get("material") in MATERIALS
                else "plastico",
                "que_hace": str(p.get("que_hace") or "")[:200],
            }
            if shape == "perfil":
                points = [
                    _vec(pt, 2, 0.0, 0.0, MAX_CM)
                    for pt in (p.get("puntos") or [])[:64]
                    if isinstance(pt, (list, tuple))
                ]
                if len(points) < 2:
                    part["forma"] = "cilindro"
                else:
                    part["puntos"] = points
            parts.append(part)
            if len(parts) >= MAX_PARTS:
                break
        if len(parts) >= MAX_PARTS:
            break
    if not parts:
        raise CreatorError("El modelo no trajo ninguna pieza.")
    used = {p["grupo"] for p in parts}
    return {
        "titulo": str(data.get("titulo") or "Modelo")[:80],
        "descripcion": str(data.get("descripcion") or "")[:400],
        "grupos": [g for g in groups if g["id"] in used],
        "piezas": parts,
    }


def _expand(p: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The part plus its mirrored copy and its copies around a circle."""
    out = [dict(p)]
    rep = p.get("repetir")
    if isinstance(rep, dict):
        count = int(_num(rep.get("n"), 1, 1, 64))
        axis = str(rep.get("eje") or "z")
        centre = _vec(rep.get("centro"), 3, 0.0)
        base = _vec(p.get("posicion"))
        rot = _vec(p.get("rotacion"), 3, 0.0, -360.0, 360.0)
        out = []
        for i in range(count):
            a = 2 * math.pi * i / count
            rel = [base[k] - centre[k] for k in range(3)]
            x, y, z = rel
            if axis == "x":
                y, z = (
                    y * math.cos(a) - z * math.sin(a),
                    y * math.sin(a) + z * math.cos(a),
                )
            elif axis == "y":
                x, z = (
                    x * math.cos(a) + z * math.sin(a),
                    -x * math.sin(a) + z * math.cos(a),
                )
            else:
                x, y = (
                    x * math.cos(a) - y * math.sin(a),
                    x * math.sin(a) + y * math.cos(a),
                )
            copy = dict(p)
            copy["posicion"] = [centre[0] + x, centre[1] + y, centre[2] + z]
            r = list(rot)
            r["xyz".index(axis) if axis in "xyz" else 2] += math.degrees(a)
            copy["rotacion"] = r
            if i:
                copy["id"] = f"{p.get('id') or p.get('nombre') or 'pieza'}-{i + 1}"
            out.append(copy)
    if p.get("espejo_x"):
        mirrored = []
        for q in out:
            m = dict(q)
            pos = _vec(q.get("posicion"))
            rot = _vec(q.get("rotacion"), 3, 0.0, -360.0, 360.0)
            m["posicion"] = [-pos[0], pos[1], pos[2]]
            m["rotacion"] = [rot[0], -rot[1], -rot[2]]
            m["id"] = f"{q.get('id') or q.get('nombre') or 'pieza'}-espejo"
            name = str(q.get("nombre") or "")
            m["nombre"] = (
                name.replace("izquierd", "derech")
                if "izquierd" in name
                else name.replace("derech", "izquierd")
                if "derech" in name
                else name + " (otro lado)"
            )
            mirrored.append(m)
        out += mirrored
    return out


PROMPT = """Eres un ingeniero y modelador 3D. Describe «{request}» como un modelo
desmontable, pieza por pieza, con medidas REALES en centímetros. Solo JSON:

{{"titulo": "...", "descripcion": "una frase",
 "grupos": [{{"id": "carroceria", "nombre": "Carrocería", "direccion": [0, 1, 0]}}, ...],
 "piezas": [{{"id": "...", "nombre": "...", "grupo": "...",
   "forma": "caja|cilindro|esfera|toro|capsula|cono|perfil",
   "medidas": [a, b, c], "redondeo": 0, "posicion": [x, y, z], "rotacion": [rx, ry, rz],
   "color": "#rrggbb", "material": "{materials}",
   "que_hace": "una frase sencilla", "espejo_x": false,
   "repetir": {{"n": 5, "eje": "z", "centro": [x, y, z]}}}}]}}

Ejes: Y hacia arriba, X a lo ancho (izquierda negativa), Z a lo largo (frente
positivo); el suelo es Y = 0. Medidas por forma: caja [ancho, alto, largo]
(con «redondeo» en cm para cantos suaves); cilindro [radio, alto, 0] (de pie
sobre Y; gíralo con «rotacion» en grados); esfera [radio, 0, 0]; toro [radio,
grosor, 0] (acostado en XZ: para una rueda, rotacion [0, 0, 90]); capsula
[radio, largo, 0]; cono [radio, alto, 0]; perfil: «puntos» [[radio, altura], …]
que se tornean alrededor de Y (llantas, faros, botellas).

Reglas:
- MUY detallado: entre 120 y 400 piezas para algo complejo (un auto: paneles,
  puertas con manija, cristales, faros, parrilla, retrovisores, ruedas con
  neumático, llanta, radios, disco, pinza y tuercas, motor con bloque, culata,
  pistones, cigüeñal, colectores, caja de cambios, ejes, suspensión,
  amortiguadores, radiador, batería, depósito, escape, asientos, volante,
  salpicadero, pedales…). Lo pequeño también cuenta.
- Lo simétrico: escribe el lado izquierdo con «espejo_x»: true. Lo que gira
  alrededor de un centro (radios, tuercas, pistones en V): «repetir».
- Cada pieza en su sitio real: que encajen, sin flotar ni atravesarse.
- Colores y materiales creíbles; «que_hace» en una frase que entienda cualquiera.
- 4 a 10 grupos, cada uno con una «direccion» distinta para separarse al
  despiezar (la carrocería hacia arriba, las ruedas hacia fuera, el motor
  hacia delante…).
- Nada de marcas, logotipos ni nombres comerciales.
Responde en {language}."""


def create(
    request: str,
    *,
    language: str = "español",
    ask: Optional[Callable[..., str]] = None,
    home: Optional[Path] = None,
) -> Dict[str, Any]:
    """Sergio draws *request* as a take-apart model; its record."""
    request = " ".join(str(request or "").split())[:300]
    if not request:
        raise CreatorError("Diga qué modelo quiere ver por piezas.")
    if ask is None:
        from openjarvis.creator.llm import ask as gemini

        ask = gemini

    def check(text: str) -> Dict[str, Any]:
        return clean(json.loads(_json_block(text)))

    text = ask(
        PROMPT.format(
            request=request, materials="|".join(MATERIALS), language=language
        ),
        json_mode=True,
        effort="medium",
        max_tokens=60000,
        check=check,
    )
    model = check(text)
    name = _free_name(slug(model["titulo"] or request), home)
    folder = root(home) / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "piezas.json").write_text(
        json.dumps(model, ensure_ascii=False), encoding="utf-8"
    )
    meta = {
        "name": name,
        "titulo": model["titulo"],
        "descripcion": model["descripcion"],
        "tipo": "piezas",
        "archivo": "piezas.json",
        "piezas": len(model["piezas"]),
        "fuente": "Dibujado por Sergio",
        "licencia": "",
    }
    _write_meta(folder, meta)
    return meta


def _json_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?|```$", "", text).strip()
    return text


def _free_name(base: str, home: Optional[Path]) -> str:
    name, n = base, 2
    while (root(home) / name).exists():
        name = f"{base}-{n}"
        n += 1
    return name


def _write_meta(folder: Path, meta: Dict[str, Any]) -> None:
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )


# -- models from files --------------------------------------------------------


def register_file(
    path: str, title: str = "", home: Optional[Path] = None
) -> Dict[str, Any]:
    """A .glb or .gltf on this computer, ready to take apart in the chat."""
    src = Path(path).expanduser()
    if not src.is_file() or src.suffix.lower() not in (".glb", ".gltf"):
        raise CreatorError("Necesito un archivo .glb o .gltf (Blender los exporta).")
    title = title or src.stem.replace("-", " ").replace("_", " ")
    name = _free_name(slug(title), home)
    folder = root(home) / name
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, folder / src.name)
    if src.suffix.lower() == ".gltf":  # its buffers and textures, next to it
        try:
            gltf = json.loads(src.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise CreatorError("Ese .gltf no se puede leer.") from exc
        for ref in [b.get("uri") for b in gltf.get("buffers", [])] + [
            i.get("uri") for i in gltf.get("images", [])
        ]:
            if ref and not str(ref).startswith("data:") and _safe_rel(str(ref)):
                extra = src.parent / ref
                if extra.is_file():
                    (folder / ref).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(extra, folder / ref)
    meta = {"name": name, "titulo": title, "descripcion": "", "tipo": "gltf", "archivo": src.name,
            "fuente": "Archivo de este equipo", "licencia": ""}  # fmt: skip
    _write_meta(folder, meta)
    return meta


def _safe_rel(rel: str) -> bool:
    p = Path(rel)
    return (
        not p.is_absolute() and ".." not in p.parts and not rel.startswith(("/", "\\"))
    )


# -- free models (CC0) --------------------------------------------------------


def search_cc0(query: str, http: Any = None, limit: int = 8) -> List[Dict[str, str]]:
    """Free (CC0) 3D models from Poly Haven whose name or tags match *query*."""
    http = http or _http()
    resp = http.get(f"{POLYHAVEN}/assets", params={"t": "models"})
    resp.raise_for_status()
    words = [w for w in slug(query).split("-") if len(w) > 2]
    hits = []
    for aid, info in (resp.json() or {}).items():
        hay = " ".join(
            [aid, str(info.get("name", ""))]
            + list(info.get("tags") or [])
            + list(info.get("categories") or [])
        )
        hay = slug(hay).replace("-", " ")
        score = sum(1 for w in words if w in hay)
        if score:
            hits.append((score, aid, str(info.get("name") or aid)))
    hits.sort(key=lambda h: (-h[0], h[2]))
    return [
        {"id": aid, "nombre": name, "licencia": "CC0"} for _s, aid, name in hits[:limit]
    ]


def download(
    asset_id: str, http: Any = None, home: Optional[Path] = None
) -> Dict[str, Any]:
    """Download a Poly Haven model (glTF, 1k textures) and get it ready."""
    if not re.fullmatch(r"[a-z0-9_]{2,80}", asset_id or ""):
        raise CreatorError("Ese modelo no existe.")
    http = http or _http()
    resp = http.get(f"{POLYHAVEN}/files/{asset_id}")
    resp.raise_for_status()
    files = resp.json() or {}
    sizes = files.get("gltf") or {}
    pick = sizes.get("1k") or sizes.get("2k") or next(iter(sizes.values()), None)
    entry = (pick or {}).get("gltf") if isinstance(pick, dict) else None
    if not entry or not entry.get("url"):
        raise CreatorError("Ese modelo no tiene versión glTF.")
    info = http.get(f"{POLYHAVEN}/info/{asset_id}")
    info_data = info.json() if getattr(info, "status_code", 200) == 200 else {}
    title = str(info_data.get("name") or asset_id.replace("_", " "))
    name = _free_name(slug(title), home)
    folder = root(home) / name
    folder.mkdir(parents=True, exist_ok=True)
    main = Path(str(entry["url"]).split("?")[0]).name
    _fetch(http, entry["url"], folder / main)
    for rel, sub in (entry.get("include") or {}).items():
        if _safe_rel(rel) and isinstance(sub, dict) and sub.get("url"):
            target = folder / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _fetch(http, sub["url"], target)
    authors = ", ".join((info_data.get("authors") or {}).keys())
    meta = {
        "name": name,
        "titulo": title,
        "descripcion": "",
        "tipo": "gltf",
        "archivo": main,
        "fuente": f"Poly Haven ({asset_id})" + (f", de {authors}" if authors else ""),
        "licencia": "CC0",
    }
    _write_meta(folder, meta)
    return meta


def _fetch(http: Any, url: str, target: Path) -> None:
    resp = http.get(url)
    resp.raise_for_status()
    target.write_bytes(resp.content)


def _http() -> Any:
    import httpx

    return httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=True,
                        headers={"User-Agent": "Sergio/1.0 (asistente personal)"})  # fmt: skip


# -- reading ------------------------------------------------------------------


def meta(name: str, home: Optional[Path] = None) -> Dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name or ""):
        raise CreatorError("Ese modelo no existe.")
    try:
        return json.loads((root(home) / name / "meta.json").read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise CreatorError("Ese modelo no existe.") from exc


def file_path(name: str, rel: str, home: Optional[Path] = None) -> Path:
    meta(name, home)  # the name is real
    if not _safe_rel(rel):
        raise CreatorError("Ese archivo no existe.")
    folder = (root(home) / name).resolve()
    path = (folder / rel).resolve()
    if folder not in path.parents or not path.is_file():
        raise CreatorError("Ese archivo no existe.")
    return path


def models(home: Optional[Path] = None) -> List[Dict[str, Any]]:
    out = []
    base = root(home)
    if base.is_dir():
        for folder in sorted(
            base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            try:
                out.append(json.loads((folder / "meta.json").read_text("utf-8")))
            except (OSError, ValueError):
                continue
    return out


__all__ = [
    "MATERIALS",
    "SHAPES",
    "clean",
    "create",
    "download",
    "file_path",
    "meta",
    "models",
    "register_file",
    "search_cc0",
    "view",
]
