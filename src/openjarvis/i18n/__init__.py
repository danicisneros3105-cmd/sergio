"""Interface language for the command line: Spanish for ``sergio``, English
for ``jarvis``.

Translations live in standard gettext catalogs (``locales/<lang>.po``) so
they can be edited with Poedit/Babel; they are parsed directly, no ``.mo``
build step. A ``msgid`` may hold numbered placeholders (``{0}``, ``{1}``)
for messages built with f-strings: the printed text is matched against the
template and the values are put back into the translation.

:func:`activate` (called by ``main()``, never by tests) translates:

* every command's ``--help`` text, walking the click command tree;
* click's own words (Usage, Options, error messages);
* text printed through Rich consoles, Rich table headers and ``click.echo``.

and names the program the user actually typed: ``jarvis config set`` reads
``sergio config set`` when Sergio is running. Untranslated text passes
through unchanged. ``SERGIO_LANG`` (or ``OPENJARVIS_LANG``) overrides the
language: ``es`` or ``en``.
"""

from __future__ import annotations

import functools
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

LANGUAGES = ("es", "en")
_LOCALES = Path(__file__).parent / "locales"
_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_PROGRAM_WORD = re.compile(r"(?<![\w./~-])jarvis(?![\w./-])")


def program_name() -> str:
    """``sergio`` or ``jarvis``, from how the command was started."""
    stem = Path(sys.argv[0] if sys.argv else "").stem.lower()
    return "sergio" if stem.startswith("sergio") else "jarvis"


def language() -> str:
    """The interface language: ``es`` or ``en``."""
    for var in ("SERGIO_LANG", "OPENJARVIS_LANG"):
        value = os.environ.get(var, "").strip().lower()[:2]
        if value in LANGUAGES:
            return value
    if program_name() == "sergio":
        return "es"
    if os.environ.get("LANG", "").lower().startswith("es"):
        return "es"
    return "en"


# -- .po parsing ---------------------------------------------------------------

_ESCAPES = {"n": "\n", "t": "\t", "b": "\b", '"': '"', "\\": "\\", "r": "\r"}


def _unquote(line: str) -> str:
    body = line.strip()[1:-1]
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), body)


def parse_po(text: str) -> Dict[str, str]:
    """``msgid -> msgstr`` from a gettext catalog (empty translations skipped)."""
    entries: Dict[str, str] = {}
    msgid: Optional[List[str]] = None
    msgstr: Optional[List[str]] = None
    current: Optional[List[str]] = None

    def flush() -> None:
        if msgid is not None and msgstr is not None:
            key, value = "".join(msgid), "".join(msgstr)
            if key and value:
                entries[key] = value

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            msgid, msgstr = [_unquote(line[6:])], None
            current = msgid
        elif line.startswith("msgstr "):
            msgstr = [_unquote(line[7:])]
            current = msgstr
        elif line.startswith('"') and current is not None:
            current.append(_unquote(line))
    flush()
    return entries


class Catalog:
    """Exact and placeholder-template translations for one language."""

    def __init__(self, entries: Dict[str, str]) -> None:
        self.exact: Dict[str, str] = {}
        self.templates: List[Tuple[re.Pattern, str]] = []
        for msgid, msgstr in entries.items():
            if _PLACEHOLDER.search(msgid):
                self.templates.append((self._pattern(msgid), msgstr))
            self.exact[self._literal(msgid)] = self._literal(msgstr)
        # Longer templates first: the most specific match wins.
        self.templates.sort(key=lambda item: -len(item[0].pattern))

    @staticmethod
    def _literal(text: str) -> str:
        return (
            text.replace("{{", "{").replace("}}", "}")
            if not _PLACEHOLDER.search(text)
            else text
        )

    @staticmethod
    def _pattern(msgid: str) -> re.Pattern:
        parts = _PLACEHOLDER.split(msgid)
        regex = []
        for i, part in enumerate(parts):
            if i % 2:
                regex.append(f"(?P<p{part}>.*?)")
            else:
                regex.append(re.escape(part.replace("{{", "{").replace("}}", "}")))
        return re.compile("^" + "".join(regex) + "$", re.S)

    def translate(self, text: str) -> str:
        hit = self.exact.get(text)
        if hit is not None:
            return hit
        for pattern, msgstr in self.templates:
            m = pattern.match(text)
            if m:
                values = {k[1:]: v for k, v in m.groupdict().items()}
                out = _PLACEHOLDER.sub(
                    lambda p: values.get(p.group(1), p.group(0)), msgstr
                )
                return out.replace("{{", "{").replace("}}", "}")
        return text


@functools.lru_cache(maxsize=4)
def catalog(lang: str) -> Catalog:
    path = _LOCALES / f"{lang}.po"
    return Catalog(parse_po(path.read_text("utf-8")) if path.is_file() else {})


def translate(
    text: str, lang: Optional[str] = None, program: Optional[str] = None
) -> str:
    """Translate *text* into *lang* and name *program* in command examples."""
    if not isinstance(text, str) or not text:
        return text
    out = catalog(lang or language()).translate(text)
    program = program or program_name()
    if program != "jarvis":
        out = _PROGRAM_WORD.sub(program, out)
    if program == "sergio":
        # One product, one name: what the owner sees is Sergio (the original
        # project keeps its credit in LICENSE/NOTICE and «Acerca de»).
        out = out.replace("OpenJarvis", "Sergio")
    return out


_ = translate


# -- activation ----------------------------------------------------------------

_active: Dict[str, object] = {}


def _localize_tree(command: Any, tr: Callable[[str], str]) -> None:
    import click

    def tr_stripped(value: str) -> str:
        # Catalog ids are stored stripped; docstrings may keep a trailing newline.
        return tr(value.strip())

    for attr in ("help", "short_help", "epilog"):
        value = getattr(command, attr, None)
        if isinstance(value, str) and value:
            setattr(command, attr, tr_stripped(value))
    for param in getattr(command, "params", ()):
        if isinstance(getattr(param, "help", None), str):
            param.help = tr_stripped(param.help)
    if isinstance(command, click.Group):
        for sub in command.commands.values():
            _localize_tree(sub, tr)


def _patch_click(tr: Callable[[str], str]) -> None:
    import click

    names = (
        "core",
        "formatting",
        "exceptions",
        "decorators",
        "termui",
        "types",
        "parser",
        "utils",
    )
    for name in names:
        module = sys.modules.get(f"click.{name}")
        if module is None:
            continue
        if callable(getattr(module, "_", None)):
            module._ = lambda s, _tr=tr: _tr(s)  # type: ignore[attr-defined]
        original_ngettext = getattr(module, "ngettext", None)
        if callable(original_ngettext):
            module.ngettext = lambda s, p, n, _o=original_ngettext, _tr=tr: _tr(
                _o(s, p, n)
            )  # type: ignore[attr-defined]
    echo = click.echo

    def _echo(message: Any = None, *args: Any, **kwargs: Any) -> Any:
        return echo(
            tr(message) if isinstance(message, str) else message, *args, **kwargs
        )

    click.echo = _echo
    for name in ("utils", "termui"):
        module = sys.modules.get(f"click.{name}")
        if module is not None and getattr(module, "echo", None) is echo:
            module.echo = _echo


def _patch_rich(tr: Callable[[str], str]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:  # pragma: no cover - rich is a core dependency
        return
    original_print = Console.print

    def _print(self: Any, *objects: Any, **kwargs: Any) -> Any:
        return original_print(
            self, *(tr(o) if isinstance(o, str) else o for o in objects), **kwargs
        )

    Console.print = _print  # type: ignore[method-assign]
    original_add_column = Table.add_column

    def _add_column(self: Any, header: Any = "", *args: Any, **kwargs: Any) -> Any:
        return original_add_column(
            self, tr(header) if isinstance(header, str) else header, *args, **kwargs
        )

    Table.add_column = _add_column  # type: ignore[method-assign]
    original_init = Table.__init__

    def _init(self: Any, *headers: Any, **kwargs: Any) -> Any:
        if isinstance(kwargs.get("title"), str):
            kwargs["title"] = tr(kwargs["title"])
        return original_init(
            self, *(tr(h) if isinstance(h, str) else h for h in headers), **kwargs
        )

    Table.__init__ = _init  # type: ignore[method-assign]


def activate(root_command: Any = None, lang: Optional[str] = None) -> str:
    """Switch the running CLI to the interface language; returns it."""
    lang = lang or language()
    program = program_name()
    if _active.get("lang") == lang:
        return lang
    if lang == "en" and program == "jarvis" and not catalog("en").exact:
        return lang

    def tr(text: str) -> str:
        return translate(text, lang, program)

    if root_command is not None:
        _localize_tree(root_command, tr)
    _patch_click(tr)
    _patch_rich(tr)
    _active["lang"] = lang
    return lang


__all__ = [
    "Catalog",
    "LANGUAGES",
    "activate",
    "catalog",
    "language",
    "parse_po",
    "program_name",
    "translate",
]
