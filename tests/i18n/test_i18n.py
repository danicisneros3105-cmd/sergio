"""Interface language: catalogs, matching, program name and full CLI coverage."""

from __future__ import annotations

import re
import subprocess
import sys

import click
import pytest

from openjarvis import i18n
from openjarvis.i18n import Catalog, catalog, parse_po, translate

PO = r"""
msgid ""
msgstr ""
"Language: es\n"

# a comment
msgid "Line one\nline \"two\"\b"
msgstr "Línea uno\nlínea \"dos\"\b"

msgid "Agent {0} created ({1})"
msgstr "Agente {0} creado ({1})"

msgid "Keep {{braces}} for {0}"
msgstr "Conserva {{llaves}} para {0}"

msgid "Untranslated"
msgstr ""

msgid "Multi "
"part"
msgstr "En "
"partes"
"""


def test_parse_po_handles_escapes_continuations_and_empty():
    entries = parse_po(PO)
    assert entries['Line one\nline "two"\b'] == 'Línea uno\nlínea "dos"\b'
    assert entries["Multi part"] == "En partes"
    assert "Untranslated" not in entries and "" not in entries


def test_templates_put_values_back_and_keep_braces():
    cat = Catalog(parse_po(PO))
    assert cat.translate("Agent bob created (abc-1)") == "Agente bob creado (abc-1)"
    assert cat.translate("Keep {braces} for x") == "Conserva {llaves} para x"
    assert cat.translate("Something else") == "Something else"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Run jarvis init first", "Run sergio init first"),
        ("``jarvis`` a secas", "``sergio`` a secas"),
        ("config in ~/.openjarvis/config.toml", "config in ~/.openjarvis/config.toml"),
        ("backend jarvis-agent", "backend jarvis-agent"),
        (
            # The product is Sergio on screen; env vars and paths keep their names.
            "OpenJarvis and JARVIS_SKIP_MODEL_PICK",
            "Sergio and JARVIS_SKIP_MODEL_PICK",
        ),
        ("module openjarvis.cli", "module openjarvis.cli"),
    ],
)
def test_program_name_in_examples(text, expected):
    assert translate(text, "en", "sergio") == expected
    assert translate(text, "en", "jarvis") == text


def test_language_precedence(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/usr/bin/sergio", "ask"])
    monkeypatch.delenv("SERGIO_LANG", raising=False)
    monkeypatch.delenv("OPENJARVIS_LANG", raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.program_name() == "sergio" and i18n.language() == "es"
    monkeypatch.setattr(sys, "argv", ["jarvis"])
    assert i18n.language() == "en"
    monkeypatch.setenv("LANG", "es_EC.UTF-8")
    assert i18n.language() == "es"
    monkeypatch.setenv("SERGIO_LANG", "en")
    assert i18n.language() == "en"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_catalog_placeholders_match(lang):
    for msgid, msgstr in parse_po(
        (i18n._LOCALES / f"{lang}.po").read_text("utf-8")
    ).items():
        assert sorted(re.findall(r"\{[^{}]*\}", msgid)) == sorted(
            re.findall(r"\{[^{}]*\}", msgstr)
        ), msgid
        assert msgid.count("\b") == msgstr.count("\b"), msgid


def _help_strings():
    from openjarvis.cli import cli

    found = []

    def walk(command, path):
        for text in (command.help, command.short_help):
            if text:
                found.append((" ".join(path), text.strip()))
        for param in command.params:
            if getattr(param, "help", None):
                found.append((" ".join(path) + f" {param.name}", param.help.strip()))
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                walk(sub, path + [name])

    walk(cli, ["sergio"])
    return found


def test_every_command_help_has_both_languages():
    """A new command needs its help in es.po (or en.po if written in Spanish)."""
    es, en = catalog("es"), catalog("en")
    missing = []
    for where, text in _help_strings():
        # English help needs a Spanish translation and vice versa; either
        # catalog covering it means the other language is served.
        if es.translate(text) == text and en.translate(text) == text:
            missing.append(f"{where}: {text[:70]!r}")
    assert not missing, "Add these to src/openjarvis/i18n/locales/*.po:\n" + "\n".join(
        missing
    )


def _run_cli(prog, *args, env=None):
    code = (
        f"import sys; sys.argv[0] = {prog!r}; from openjarvis.cli import main; main()"
    )
    import os

    run_env = dict(os.environ, OPENJARVIS_NO_UPDATE_CHECK="1", **(env or {}))
    run_env.pop("SERGIO_LANG", None)
    run_env.pop("OPENJARVIS_LANG", None)
    run_env.update(env or {})
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        env=run_env,
        timeout=120,
    )


def test_sergio_speaks_spanish_and_jarvis_english():
    es = _run_cli("sergio", "ask", "--help")
    assert (
        "Uso: sergio ask" in es.stdout and "Hazle una pregunta a Sergio." in es.stdout
    )
    assert "Muestra este mensaje y sale." in es.stdout
    en = _run_cli("jarvis", "ask", "--help", env={"LANG": "C.UTF-8"})
    assert "Usage: jarvis ask" in en.stdout and "Ask Jarvis a question." in en.stdout
    forced = _run_cli("sergio", "pensar", "--help", env={"SERGIO_LANG": "en"})
    assert "Think deeply" in forced.stdout


def test_click_errors_are_translated():
    out = _run_cli("sergio", "nonexistent")
    assert "No existe el comando 'nonexistent'." in out.stderr
    assert "Prueba 'sergio --help' para ver la ayuda." in out.stderr
