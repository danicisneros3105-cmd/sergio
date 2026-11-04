"""Tools: Sergio works in the background, makes Excel files and finds photos.

* ``en_segundo_plano``: a browser of Sergio's own, without a window, so the
  person keeps using the screen (a film, a call) while Sergio checks a site
  they are signed in to («¿tengo tareas pendientes en la plataforma del
  colegio?»). Never sends, pays, books, publishes or deletes: those steps stop
  and wait for the person's yes.
* ``hoja_calculo``: a real .xlsx (formats, totals with formulas) from rows, and
  reading .xlsx/.csv files back.
* ``buscar_fotos``: pictures in the person's own folders, by date, name, kind
  and, if asked, by what they show.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
from pathlib import Path
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


def _ok(tool: str, data: Any) -> ToolResult:
    text = (
        data
        if isinstance(data, str)
        else json.dumps(data, ensure_ascii=False, default=str)
    )
    return ToolResult(tool_name=tool, content=text, success=True)


def _fail(tool: str, why: str) -> ToolResult:
    return ToolResult(tool_name=tool, content=why, success=False)


@ToolRegistry.register("en_segundo_plano")
class SegundoPlanoTool(BaseTool):
    tool_id = "en_segundo_plano"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="en_segundo_plano",
            description=(
                "Check a website WITHOUT taking the screen (Sergio's own browser, no window), "
                "so the person keeps watching or working: school platform, bank balance page, "
                "orders, mail web, any site they signed in to once. action='revisar' with "
                "'sitio' (saved name like 'colegio', or https URL) and optional 'pasos' "
                "[{ir|clic|escribir+campo|tecla|esperar}] returns the page text: answer the "
                "person from it. 'necesita_sesion' → offer action='iniciar_sesion' (opens a "
                "window where THEY sign in once; never ask for passwords). 'guardar_sitio' "
                "(nombre, url) remembers «mi colegio = …»; 'sitios' lists them. Steps that "
                "send, pay, buy, book, publish or delete stop with 'espera_su_si': ask first. "
                "LEAVE IT RUNNING (answer at once, the person keeps going): 'luego' = read the "
                "site in the background and notify when done; 'vigilar' (sitio, cada_min, "
                "optional buscar = a word to wait for) checks every N minutes and notifies on a "
                "change; 'tareas' lists them with results; 'cancelar' (id) stops one."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "revisar",
                            "iniciar_sesion",
                            "guardar_sitio",
                            "sitios",
                            "olvidar_sitio",
                            "luego",
                            "vigilar",
                            "tareas",
                            "cancelar",
                        ],
                    },
                    "sitio": {"type": "string"},
                    "nombre": {"type": "string"},
                    "url": {"type": "string"},
                    "nota": {"type": "string"},
                    "pasos": {"type": "array", "items": {"type": "object"}},
                    "cada_min": {"type": "number"},
                    "buscar": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["action"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.asistente import navegador as nav

        action = str(params.get("action") or "")
        try:
            if action == "sitios":
                return _ok(
                    self.tool_id, nav.sites() or "No hay sitios guardados todavía."
                )
            if action == "guardar_sitio":
                item = nav.save_site(str(params.get("nombre") or ""), str(params.get("url") or ""),
                                     str(params.get("nota") or ""))  # fmt: skip
                return _ok(self.tool_id, {"guardado": item})
            if action == "olvidar_sitio":
                done = nav.forget_site(
                    str(params.get("nombre") or params.get("sitio") or "")
                )
                return _ok(
                    self.tool_id, "Olvidado." if done else "No lo tenía guardado."
                )
            target = str(params.get("sitio") or params.get("url") or "")
            if action in ("luego", "vigilar", "tareas", "cancelar"):
                from openjarvis.asistente import tareas

                if action == "tareas":
                    rows = [tareas.plain(t) for t in tareas.load()[-12:]]
                    return _ok(self.tool_id, rows or "No hay tareas en segundo plano.")
                if action == "cancelar":
                    done = tareas.cancel(str(params.get("id") or ""))
                    return _ok(
                        self.tool_id, "Detenida." if done else "No estaba en marcha."
                    )
                steps = params.get("pasos") or []
                task = tareas.start(
                    "vigilar" if action == "vigilar" else "revisar",
                    target,
                    pasos=steps if isinstance(steps, list) else [],
                    cada_min=float(params.get("cada_min") or 30),
                    buscar=str(params.get("buscar") or ""),
                )
                return _ok(
                    self.tool_id,
                    {"en_marcha": tareas.plain(task),
                     "nota": "Sigue en segundo plano; avisa en la pantalla al terminar o si cambia."},
                )  # fmt: skip
            if action == "iniciar_sesion":
                return _ok(self.tool_id, nav.open_to_sign_in(target))
            if action == "revisar":
                steps = params.get("pasos") or []
                return _ok(
                    self.tool_id,
                    nav.check(target, steps if isinstance(steps, list) else []),
                )
        except nav.NavegadorError as exc:
            return _fail(self.tool_id, str(exc))
        except Exception as exc:  # noqa: BLE001 — the site, not Sergio: say what happened
            return _fail(self.tool_id, f"No pude leer el sitio: {str(exc)[:200]}")
        return _fail(self.tool_id, "Acción desconocida.")


def _documents() -> Path | None:
    """The person's Documents/Sergio folder (Windows from WSL, or the home)."""
    users = Path("/mnt/c/Users")
    candidates = []
    if users.is_dir():
        for u in users.iterdir():
            if u.name.lower() in ("public", "default", "default user", "all users"):
                continue
            candidates += [
                u / "Documents",
                u / "OneDrive" / "Documents",
                u / "Documentos",
            ]
    candidates += [Path.home() / "Documents", Path.home() / "Documentos"]
    for c in candidates:
        try:
            if c.is_dir():
                return c / "Sergio"
        except OSError:
            continue
    return None


@ToolRegistry.register("hoja_calculo")
class HojaCalculoTool(BaseTool):
    tool_id = "hoja_calculo"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="hoja_calculo",
            description=(
                "Excel (.xlsx). action='leer' with 'ruta' (.xlsx or .csv) returns its sheets' rows "
                "(read an expense report, a list…). action='crear' with 'titulo' and 'hojas': "
                "[{nombre, columnas, filas, formatos:{col: texto|numero|moneda|porcentaje|fecha}, "
                "totales:[cols to SUM]}] writes a real workbook (bold frozen header, filters, "
                "live formulas; a cell can be a formula like '=SUM(D2:D9)'). Put the person's real "
                "data only, never invented numbers. Returns where it was saved and a download link."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["crear", "leer"]},
                    "titulo": {"type": "string"},
                    "hojas": {"type": "array", "items": {"type": "object"}},
                    "ruta": {"type": "string"},
                },
                "required": ["action"],
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.asistente import xlsx

        action = str(params.get("action") or "")
        try:
            if action == "leer":
                path = Path(str(params.get("ruta") or "")).expanduser()
                if not path.is_file():
                    return _fail(self.tool_id, f"No encuentro {path}.")
                sheets = xlsx.read(path, max_rows=500)
                return _ok(self.tool_id, {"hojas": sheets})
            if action == "crear":
                from openjarvis.creator import studio

                title = str(params.get("titulo") or "Hoja de Sergio").strip()[:80]
                slug = re.sub(r"[^\w\-]+", "-", title.lower()).strip("-")[:40] or "hoja"
                name = f"{slug}-{secrets.token_hex(12)}.xlsx"
                path = xlsx.write(
                    studio.projects_root() / "documentos" / name,
                    list(params.get("hojas") or []),
                )
                out: dict = {
                    "archivo": str(path),
                    "descargar": f"/v1/creator/archivo/{path.name}",
                }
                docs = _documents()
                if docs is not None:
                    try:
                        docs.mkdir(parents=True, exist_ok=True)
                        copy = docs / f"{slug}.xlsx"
                        shutil.copy2(path, copy)
                        out["en_documentos"] = str(copy)
                    except OSError:
                        pass
                return _ok(self.tool_id, out)
        except xlsx.XlsxError as exc:
            return _fail(self.tool_id, str(exc))
        except (OSError, ValueError, KeyError) as exc:
            return _fail(self.tool_id, f"No pude con el archivo: {str(exc)[:200]}")
        return _fail(self.tool_id, "Acción desconocida.")


@ToolRegistry.register("buscar_fotos")
class BuscarFotosTool(BaseTool):
    tool_id = "buscar_fotos"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="buscar_fotos",
            description=(
                "Find photos in the person's OWN folders (Pictures, OneDrive, Desktop, Downloads). "
                "Filters: 'desde'/'hasta' (YYYY-MM-DD, date taken), 'nombre' (words in the file or "
                "folder name), 'capturas' (true = screenshots only, false = no screenshots), "
                "'orientacion' (vertical|horizontal). 'que_muestra' (e.g. 'un perro en la playa') "
                "makes the vision model look at small thumbnails of the candidates: narrow by "
                "date first when you can. Returns paths and dates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "que_muestra": {"type": "string"},
                    "nombre": {"type": "string"},
                    "desde": {"type": "string"},
                    "hasta": {"type": "string"},
                    "capturas": {"type": "boolean"},
                    "orientacion": {
                        "type": "string",
                        "enum": ["vertical", "horizontal"],
                    },
                    "cuantas": {"type": "integer"},
                },
            },
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.asistente import fotos

        res = fotos.find(
            what=str(params.get("que_muestra") or ""),
            name=str(params.get("nombre") or ""),
            since=str(params.get("desde") or ""),
            until=str(params.get("hasta") or ""),
            screenshots=params.get("capturas"),
            orientation=str(params.get("orientacion") or ""),
            limit=max(1, min(60, int(params.get("cuantas") or 24))),
        )
        return _ok(self.tool_id, res)


__all__ = ["BuscarFotosTool", "HojaCalculoTool", "SegundoPlanoTool"]
