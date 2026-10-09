"""Plugins: manifest rules, safe archives, install/uninstall, loading, CLI."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from openjarvis.core.registry import ToolRegistry
from openjarvis.plugins import loader
from openjarvis.plugins.index import CATALOG, search
from openjarvis.plugins.manifest import ManifestError, parse_manifest, version_key
from openjarvis.plugins.package import PackageError, pack, read_manifest, unpack
from openjarvis.plugins.store import PluginError, PluginStore

TOML = """[plugin]
name = "{name}"
version = "{version}"
description = "demo"
entry = "plugin.py"
permissions = {perms}
"""
CODE = """
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


class Eco(BaseTool):
    tool_id = "{tool}"

    @property
    def spec(self):
        return ToolSpec(name="{tool}", description="eco", parameters={{}}, required_capabilities={caps})

    def execute(self, **params):
        return ToolResult(tool_name="{tool}", content="eco", success=True)


def register(api):
    api.tool(Eco)
"""


def make_plugin(
    root: Path, name="eco", version="1.0.0", perms="[]", tool="eco_tool", caps="[]"
) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "plugin.toml").write_text(
        TOML.format(name=name, version=version, perms=perms)
    )
    (folder / "plugin.py").write_text(CODE.format(tool=tool, caps=caps))
    return folder


def zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("SERGIO_NO_PLUGINS", raising=False)
    monkeypatch.setattr(loader, "_LOADED", {})
    monkeypatch.setattr(loader, "_FAILED", {})
    monkeypatch.setattr(loader, "_CLASSES", {})
    return tmp_path


# -- manifest -------------------------------------------------------------------


def test_manifest_rules():
    m = parse_manifest(
        TOML.format(name="ok-name", version="1.2.3", perms='["network:fetch"]')
    )
    assert m.permissions == ["network:fetch"] and m.permissions_es() == [
        "conectarse a internet"
    ]
    bad = [
        TOML.format(name="Bad Name", version="1.0.0", perms="[]"),
        TOML.format(name="ok", version="one", perms="[]"),
        TOML.format(name="ok", version="1.0.0", perms='["teleport"]'),
        TOML.format(name="ok", version="1.0.0", perms='["channel:send"]'),
        TOML.format(name="ok", version="1.0.0", perms='["system:admin"]'),
        "[plugin]\nname='ok'\nversion='1.0.0'\nentry='../evil.py'",
        "nope = [",
    ]
    for text in bad:
        with pytest.raises(ManifestError):
            parse_manifest(text)
    assert version_key("1.10.0") > version_key("1.9.2") > version_key("1.9.2-rc1")


# -- archives -------------------------------------------------------------------


def test_pack_and_unpack_round_trip(tmp_path):
    folder = make_plugin(tmp_path / "src")
    (folder / "__pycache__").mkdir()
    (folder / "__pycache__" / "x.pyc").write_bytes(b"x")
    archive, digest, manifest = pack(folder, tmp_path / "out")
    assert archive.name == "eco-1.0.0.zip" and len(digest) == 64
    names = zipfile.ZipFile(archive).namelist()
    assert sorted(names) == ["plugin.py", "plugin.toml"]
    again, digest2, _ = pack(folder, tmp_path / "out2")
    assert digest2 == digest  # reproducible
    assert unpack(archive.read_bytes(), tmp_path / "dest").name == "eco"


@pytest.mark.parametrize(
    "evil",
    [
        "../escape.py",
        "/abs.py",
        "C:\\x.py",
        "dir/../../up.py",
        "run.exe",
        "lib.so",
        "go.sh",
    ],
)
def test_unpack_refuses_dangerous_entries(tmp_path, evil):
    data = zip_bytes(
        {
            "plugin.toml": TOML.format(name="eco", version="1.0.0", perms="[]"),
            "plugin.py": "x",
            evil: "x",
        }
    )
    with pytest.raises(PackageError):
        unpack(data, tmp_path / "dest")
    assert not (tmp_path / "escape.py").exists()


def test_archive_without_manifest_or_entry(tmp_path):
    with pytest.raises(PackageError):
        read_manifest(zip_bytes({"plugin.py": "x"}))
    with pytest.raises(PackageError):
        read_manifest(b"not a zip")
    with pytest.raises(PackageError):
        unpack(
            zip_bytes(
                {"plugin.toml": TOML.format(name="eco", version="1.0.0", perms="[]")}
            ),
            tmp_path / "d",
        )


# -- store and loader -----------------------------------------------------------


def test_install_load_disable_uninstall(home):
    archive, digest, _ = pack(make_plugin(home / "src"), home / "out")
    store = PluginStore()
    with pytest.raises(PluginError, match="huella"):
        store.install(archive.read_bytes(), expected_sha256="0" * 64)
    store.install(archive.read_bytes(), expected_sha256=digest, source="test")
    assert store.installed()["eco"]["sha256"] == digest and store.enabled() == ["eco"]
    with pytest.raises(PluginError, match="ya está instalado"):
        store.install(archive.read_bytes())
    assert loader.load_enabled() == {"eco": ["eco_tool"]}
    assert ToolRegistry.contains("eco_tool")
    assert ToolRegistry.get("eco_tool")().execute().content == "eco"
    # Tests clear the registry; loading again puts the tool back.
    ToolRegistry.clear()
    loader.load_enabled()
    assert ToolRegistry.contains("eco_tool")
    store.set_enabled("eco", False)
    loader.forget("eco")
    assert not ToolRegistry.contains("eco_tool") and loader.load_enabled() == {}
    store.uninstall("eco")
    assert not (store.root / "eco").exists() and store.installed() == {}
    with pytest.raises(PluginError):
        store.uninstall("eco")


def test_update_replaces_the_old_version(home):
    store = PluginStore()
    store.install(pack(make_plugin(home / "a"), home / "o1")[0].read_bytes())
    store.install(
        pack(make_plugin(home / "b", version="1.1.0"), home / "o2")[0].read_bytes()
    )
    assert store.installed()["eco"]["version"] == "1.1.0"
    assert store.manifest("eco").version == "1.1.0"
    assert not any(p.name.startswith((".tmp-", ".old-")) for p in store.root.iterdir())


def test_loader_refuses_undeclared_capabilities_and_builtin_names(home):
    import openjarvis.tools  # noqa: F401 - built-ins registered

    ToolRegistry.restore_builtin()
    store = PluginStore()
    greedy = make_plugin(
        home / "g", name="greedy", tool="greedy_tool", caps='["network:fetch"]'
    )
    store.install(pack(greedy, home / "o1")[0].read_bytes())
    clash = make_plugin(home / "c", name="clash", tool="calculator")
    store.install(pack(clash, home / "o2")[0].read_bytes())
    loaded = loader.load_enabled()
    assert loaded == {}
    failed = loader.status()["failed"]
    assert (
        "no declaró" in failed["greedy"] and "ya es una herramienta" in failed["clash"]
    )
    assert ToolRegistry.get("calculator").__module__.startswith("openjarvis.")


def test_bundled_catalog_installs_and_works(home):
    assert {e.name for e in search("")} >= {"frase-del-dia", "tipo-de-cambio"}
    assert search("monedas")[0].name == "tipo-de-cambio"
    from openjarvis.plugins.index import fetch, find

    store = PluginStore()
    store.install(fetch(find("frase-del-dia")))
    assert loader.load_enabled()["frase-del-dia"] == ["frase_del_dia"]
    result = ToolRegistry.get("frase_del_dia")().execute()
    phrases = json.loads(
        (CATALOG / "frase-del-dia" / "assets" / "frases.json").read_text()
    )
    assert result.success and result.content in phrases


# -- CLI ------------------------------------------------------------------------


def test_cli_flow(home):
    from openjarvis.cli.plugin_cmd import plugin

    runner = CliRunner()
    out = runner.invoke(plugin, ["buscar", "refrán"]).output
    assert "frase-del-dia" in out
    refused = runner.invoke(plugin, ["instalar", "tipo-de-cambio"], input="n\n")
    assert "conectarse a internet" in refused.output and "No instalé" in refused.output
    ok = runner.invoke(plugin, ["install", "frase-del-dia", "--si"])
    assert ok.exit_code == 0 and "frase_del_dia" in ok.output, ok.output
    assert "frase-del-dia 1.0.0" in runner.invoke(plugin, ["lista"]).output
    assert (
        "Herramientas: frase_del_dia"
        in runner.invoke(plugin, ["info", "frase-del-dia"]).output
    )
    assert (
        "desactivado" in runner.invoke(plugin, ["desactivar", "frase-del-dia"]).output
    )
    assert "activado" in runner.invoke(plugin, ["enable", "frase-del-dia"]).output
    assert (
        "desinstalado" in runner.invoke(plugin, ["uninstall", "frase-del-dia"]).output
    )
    missing = runner.invoke(plugin, ["instalar", "no-existe"])
    assert missing.exit_code != 0 and "no encuentro" in missing.output


def test_cli_create_pack_install(home, tmp_path):
    from openjarvis.cli.plugin_cmd import plugin

    runner = CliRunner()
    made = runner.invoke(plugin, ["crear", "mi-plugin", "--carpeta", str(tmp_path)])
    assert made.exit_code == 0, made.output
    packed = runner.invoke(
        plugin,
        ["empaquetar", str(tmp_path / "mi-plugin"), "--salida", str(tmp_path / "dist")],
    )
    assert packed.exit_code == 0 and "sha256:" in packed.output, packed.output
    zip_path = tmp_path / "dist" / "mi-plugin-0.1.0.zip"
    done = runner.invoke(plugin, ["instalar", str(zip_path), "--si"])
    assert done.exit_code == 0 and "mi_plugin" in done.output, done.output
    assert ToolRegistry.get("mi_plugin")().execute(texto="hola").content == "HOLA"
