"""Local full-text index of the prompt library (SQLite FTS5, ranked by BM25)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from openjarvis.prompt_library.clean import (
    ASSISTANTS,
    COMPANIES,
    clean_text,
    is_jailbreak,
    is_jailbreak_file,
    names_pattern,
    passages,
)
from openjarvis.prompt_library.sources import Source, all_sources

TEXT_TYPES = {".md", ".txt", ".j2", ".yml", ".yaml", ".json", ".xml", ".prompt", ".mdx"}
SKIP_NAMES = re.compile(
    r"^(readme|license|licence|contributing|code_of_conduct|changelog|security|"
    r"package(-lock)?|tsconfig|\.)",
    re.I,
)
MAX_FILE = 3_000_000
KIND_LABEL = {
    "sistema": "prompt de sistema",
    "rol": "prompt de rol",
    "personaje": "prompt de personaje",
}

# Titles come from folder names in lower case, so they are neutralized ignoring case.
_TITLE_NAMES = names_pattern(ASSISTANTS + COMPANIES, re.I)


def library_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "prompt_library"


def _title(*parts: str) -> str:
    words = " · ".join(p for p in parts if p)
    words = re.sub(r"[_-]+", " ", words)
    words = re.sub(r"\b\d{4} ?\d{2} ?\d{2}\b|\b\d{8}\b", "", words)
    words = _TITLE_NAMES.sub("asistente", words)
    return re.sub(r"\s+", " ", words).strip(" ·") or "prompt"


@contextmanager
def _db(path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(str(path), timeout=10)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS passages;
        DROP TABLE IF EXISTS meta;
        CREATE VIRTUAL TABLE passages USING fts5(
            title, body, source UNINDEXED, kind UNINDEXED, file UNINDEXED,
            tokenize = 'porter unicode61 remove_diacritics 2'
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )


def _json_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        if len(value) >= 200:
            yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _json_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _json_strings(v)


def _file_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        try:
            return "\n\n".join(_json_strings(json.loads(raw)))
        except ValueError:
            return ""
    return raw


def _roles(path: Path) -> Iterator[tuple[str, str]]:
    csv.field_size_limit(10**8)
    with path.open(encoding="utf-8", errors="ignore", newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("type") or "").upper() == "IMAGE":
                continue
            act, prompt = (row.get("act") or "").strip(), row.get("prompt") or ""
            if not act or not prompt or is_jailbreak(act) or is_jailbreak(prompt):
                continue
            yield _title(act), clean_text(prompt)


def _files(root: Path, source: Source) -> Iterator[Path]:
    tops = [root / p for p in source.paths] if source.paths else [root]
    for top in tops:
        if top.is_file():
            yield top
            continue
        for path in sorted(top.rglob("*")):
            rel = path.relative_to(root).parts
            if ".git" in rel or not path.is_file() or path.is_symlink():
                continue
            if path.suffix.lower() not in TEXT_TYPES or SKIP_NAMES.match(path.name):
                continue
            if path.stat().st_size > MAX_FILE:
                continue
            yield path


def build(
    folder: Optional[Path] = None, sources: Optional[Sequence[Source]] = None
) -> Dict[str, Any]:
    """(Re)build ``index.db`` from whatever is in ``repos/``; returns counts."""
    folder = folder or library_dir()
    sources = list(sources) if sources is not None else all_sources(folder)
    target = folder / "index.db"
    temp = folder / "index.db.tmp"
    temp.unlink(missing_ok=True)
    counts: Dict[str, Dict[str, int]] = {}
    with _db(temp) as con:
        _schema(con)
        for source in sources:
            root = folder / "repos" / source.key
            if not root.is_dir():
                continue
            files = kept = dropped = 0
            for path in _files(root, source):
                files += 1
                rel = path.relative_to(root)
                if path.suffix.lower() == ".csv":
                    rows = list(_roles(path))
                else:
                    raw = _file_text(path)
                    if is_jailbreak_file(path.name, raw):
                        dropped += 1
                        continue
                    # Headings only: folder and file names are other products' names.
                    rows = [
                        (_title(h) if h else KIND_LABEL[source.kind], b)
                        for h, b in passages(clean_text(raw), "")
                    ]
                for title, body in rows:
                    if len(body) < 80:
                        continue
                    con.execute(
                        "INSERT INTO passages (title, body, source, kind, file) VALUES (?,?,?,?,?)",
                        (title, body, source.key, source.kind, str(rel)),
                    )
                    kept += 1
            counts[source.key] = {
                "files": files,
                "passages": kept,
                "dropped_files": dropped,
            }
        con.execute("INSERT INTO meta VALUES ('built_at', ?)", (str(int(time.time())),))
        con.execute("INSERT INTO meta VALUES ('counts', ?)", (json.dumps(counts),))
        con.execute("INSERT INTO passages(passages) VALUES ('optimize')")
    temp.replace(target)
    _cache.clear()
    return counts


# --- search -------------------------------------------------------------------

_STOP = set(
    """a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada como con contra cual
    cuando de del desde donde dos el ella ellas ellos en entre era es esa esas ese eso esos esta estas
    este esto estos fue ha hace hacer hay haz la las le les lo los mas me mi mis muy nada ni no nos nuestra
    nuestro o otra otro para pero poco por porque puede pues que quien se sea ser si sin sobre solo son su
    sus tambien te tengo ti tiene todo todos tu tus un una unas uno unos usted ya yo quiero quisiera
    necesito podrias puedes dame dime favor gracias senor sergio por favor hola oye
    the and for with that this from into your you are can will what how why when which who about please
    have has had was were been being would could should there their them they then than also just like
    me my our its it is be to of in on at by an or as do does did not no so if""".split()
)

# Requests arrive in Spanish while most of the library is in English.
GLOSSARY = {
    "codigo": "code",
    "programar": "code programming",
    "programa": "program",
    "funcion": "function",
    "error": "error bug",
    "errores": "errors bugs",
    "arreglar": "fix",
    "arregla": "fix",
    "depurar": "debug",
    "prueba": "test",
    "pruebas": "tests testing",
    "base": "database",
    "datos": "data",
    "archivo": "file",
    "archivos": "files",
    "carpeta": "folder directory",
    "pagina": "page website",
    "web": "web website",
    "sitio": "website",
    "aplicacion": "app application",
    "diseno": "design",
    "disena": "design",
    "interfaz": "interface ui",
    "boton": "button",
    "imagen": "image",
    "imagenes": "images",
    "foto": "photo",
    "video": "video",
    "musica": "music",
    "cancion": "song",
    "escribir": "write writing",
    "escribe": "write",
    "redacta": "write draft",
    "correo": "email",
    "carta": "letter",
    "resumen": "summary",
    "resume": "summarize",
    "resumir": "summarize",
    "traducir": "translate",
    "traduce": "translate",
    "idioma": "language",
    "investigar": "research",
    "investiga": "research",
    "investigacion": "research",
    "buscar": "search",
    "busca": "search",
    "fuentes": "sources citations",
    "noticias": "news",
    "explica": "explain",
    "explicar": "explain",
    "ensenar": "teach tutor",
    "aprender": "learn learning",
    "estudiar": "study",
    "examen": "exam",
    "tarea": "task homework",
    "tareas": "tasks",
    "plan": "plan planning",
    "planificar": "plan",
    "agenda": "schedule calendar",
    "reunion": "meeting",
    "negocio": "business",
    "empresa": "company business",
    "ventas": "sales",
    "marketing": "marketing",
    "precio": "price pricing",
    "dinero": "money finance",
    "finanzas": "finance",
    "inversion": "investment",
    "estrategia": "strategy",
    "analisis": "analysis",
    "analiza": "analyze",
    "grafico": "chart graph",
    "tabla": "table spreadsheet",
    "hoja": "spreadsheet sheet",
    "salud": "health",
    "mental": "mental",
    "ansiedad": "anxiety",
    "estres": "stress",
    "dormir": "sleep",
    "sueno": "sleep",
    "ejercicio": "exercise workout",
    "dieta": "diet nutrition",
    "comida": "food",
    "receta": "recipe",
    "medico": "doctor medical",
    "terapia": "therapy therapist",
    "psicologo": "psychologist",
    "emociones": "emotions",
    "triste": "sad",
    "consejo": "advice",
    "ayuda": "help",
    "historia": "story history",
    "cuento": "story",
    "poema": "poem poetry",
    "chiste": "joke humor",
    "juego": "game",
    "personaje": "character persona",
    "actua": "act role",
    "rol": "role",
    "entrevista": "interview",
    "trabajo": "job work",
    "curriculum": "resume cv",
    "abogado": "lawyer legal",
    "contrato": "contract",
    "ley": "law legal",
    "viaje": "travel trip",
    "viajar": "travel",
    "ciudad": "city",
    "seguridad": "security",
    "contrasena": "password",
    "red": "network",
    "servidor": "server",
    "nube": "cloud",
    "terminal": "terminal shell",
    "comando": "command",
    "script": "script",
    "automatizar": "automate",
    "agente": "agent",
    "herramienta": "tool",
    "herramientas": "tools",
    "pantalla": "screen",
    "navegador": "browser",
    "modelo": "model",
    "prompt": "prompt",
    "instrucciones": "instructions",
    "revisar": "review",
    "revisa": "review",
    "mejorar": "improve",
    "mejora": "improve",
    "optimizar": "optimize",
    "rapido": "fast performance",
    "presentacion": "presentation slides",
    "diapositivas": "slides",
    "documento": "document",
    "libro": "book",
    "matematicas": "math",
    "fisica": "physics",
    "quimica": "chemistry",
    "ciencia": "science",
    "filosofia": "philosophy",
    "pensar": "reasoning think",
    "razonar": "reasoning",
    "decision": "decision",
    "decidir": "decide",
    "logo": "logo brand",
    "marca": "brand",
    "tienda": "store shop",
    "cliente": "customer client",
    "clientes": "customers",
    "producto": "product",
    "3d": "3d",
    "modelar": "modeling",
    "ansioso": "anxious anxiety",
    "ansiosa": "anxious anxiety",
    "deprimido": "depressed depression",
    "deprimida": "depressed depression",
    "preocupado": "worried worry",
    "preocupada": "worried worry",
    "soledad": "loneliness lonely",
    "pareja": "partner relationship",
    "relacion": "relationship",
    "familia": "family",
    "amigo": "friend",
    "amigos": "friends",
    "autoestima": "self-esteem confidence",
    "motivacion": "motivation",
    "habito": "habit",
    "habitos": "habits",
    "entrevistador": "interviewer interview",
    "profesor": "teacher tutor",
    "tutor": "tutor",
    "traductor": "translator",
    "escritor": "writer",
    "editor": "editor editing",
    "critico": "critic review",
    "coach": "coach",
    "entrenador": "trainer coach",
    "nutricionista": "nutritionist",
    "medicina": "medicine medical",
    "sintoma": "symptom",
}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def query_terms(text: str, limit: int = 18) -> List[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+#.]*[a-z0-9+#]|[a-z0-9]", _fold(text))
    terms: List[str] = []
    for word in words:
        if word in _STOP or len(word) < 2:
            continue
        for term in [word, *GLOSSARY.get(word, "").split()]:
            term = term.strip(".")
            if term and term not in terms and term not in _STOP:
                terms.append(term)
    return terms[:limit]


_cache: Dict[str, Any] = {}


def _index(folder: Optional[Path] = None) -> Optional[Path]:
    path = (folder or library_dir()) / "index.db"
    return path if path.is_file() else None


def search(
    text: str,
    k: int = 3,
    *,
    kinds: Optional[Sequence[str]] = None,
    folder: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """The *k* passages that best match *text*, one per file at most."""
    path = _index(folder)
    terms = query_terms(text)
    if path is None or not terms:
        return []
    expr = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
    sql = (
        "SELECT title, body, source, kind, file FROM passages WHERE passages MATCH ? "
        + (f"AND kind IN ({','.join('?' * len(kinds))}) " if kinds else "")
        + "ORDER BY bm25(passages, 3.0, 1.0) LIMIT ?"
    )
    args: List[Any] = [expr, *(kinds or []), k * 8]
    try:
        with _db(path) as con:
            rows = con.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []
    need = 1 if len(terms) <= 2 else max(2, round(len(terms) * 0.3))
    found: List[Dict[str, str]] = []
    seen = set()
    for title, body, source, kind, file in rows:
        haystack = _fold(f"{title} {body}")
        hits = sum(1 for t in terms if t in haystack)
        key = body[:200]
        if hits < need or (source, file) in seen or key in seen:
            continue
        seen.update([(source, file), key])
        found.append(
            {"title": title, "body": body, "source": source, "kind": kind, "file": file}
        )
        if len(found) >= k:
            break
    return found


def status(folder: Optional[Path] = None) -> Dict[str, Any]:
    folder = folder or library_dir()
    path = _index(folder)
    out: Dict[str, Any] = {
        "installed": path is not None,
        "folder": str(folder),
        "sources": [],
    }
    meta: Dict[str, str] = {}
    total = 0
    if path is not None:
        try:
            with _db(path) as con:
                meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
                total = con.execute("SELECT count(*) FROM passages").fetchone()[0]
        except sqlite3.Error:
            out["installed"] = False
    counts = json.loads(meta.get("counts") or "{}")
    synced = _read_sync(folder)
    for source in all_sources(folder):
        row = counts.get(source.key, {})
        out["sources"].append(
            {
                "key": source.key,
                "repo": source.repo,
                "kind": KIND_LABEL.get(source.kind, source.kind),
                "license": source.license,
                "about": source.about,
                "files": row.get("files", 0),
                "passages": row.get("passages", 0),
                "commit": synced.get(source.key, {}).get("commit", ""),
                "error": synced.get(source.key, {}).get("error", ""),
            }
        )
    out["passages"] = total
    out["built_at"] = int(meta.get("built_at") or 0)
    return out


def _read_sync(folder: Path) -> Dict[str, Dict[str, str]]:
    try:
        return json.loads((folder / "sync.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


__all__ = ["GLOSSARY", "build", "library_dir", "query_terms", "search", "status"]
