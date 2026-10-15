"""``sergio mcp`` end to end, against real servers built with the official SDK."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent))
real = pytest.importorskip("real_servers")
warnings.filterwarnings("ignore")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    import openjarvis.mcp.hub as hub_module

    monkeypatch.setattr(hub_module, "_hub", None)
    return tmp_path


@pytest.fixture(scope="module")
def site():
    port = real.free_port()
    base = f"http://127.0.0.1:{port}"
    provider = real.MemoryProvider()
    real.serve(real.oauth_server(base, provider).streamable_http_app(), port)
    yield base
    real.stop_all()


def run(*args: str) -> str:
    from openjarvis.cli.mcp_cmd import mcp

    result = CliRunner().invoke(mcp, list(args), catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result.output


def test_add_login_list_call_permission_remove(home, site, monkeypatch):
    # The «browser» is curl: it opens the service page and follows it back.
    monkeypatch.setenv("BROWSER", "curl -s -o /dev/null -L %s")
    assert "Añadido" in run("add", "--transport", "http", "protegido", f"{site}/mcp")
    out = run("login", "protegido")
    assert "conectado" in out and "2 herramientas" in out
    assert "✓ protegido" in run("list")
    assert run("call", "protegido", "sumar", '{"a": 40, "b": 2}').strip() == "42"
    run("permiso", "protegido", "sumar", "block")
    assert "Nunca" in run("tools", "protegido")
    run("logout", "protegido")
    assert "falta iniciar sesión" in run("get", "protegido")
    run("remove", "protegido")
    assert "Ningún conector" in run("list")


def test_directory_and_add_by_name(home):
    assert "notion" in run("directorio", "notion")
    assert "Notion" in run("add", "notion")
    assert "https://mcp.notion.com/mcp" in run("get", "notion")


def test_add_json_local_and_claude_desktop_import(home, tmp_path, monkeypatch):
    script = tmp_path / "srv.py"
    script.write_text(
        f"import sys\nsys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "from real_servers import tool_server\ntool_server().run()\n"
    )
    run(
        "add-json",
        "local",
        json.dumps({"command": sys.executable, "args": [str(script)]}),
    )
    assert "✓ local" in run("list")
    config = tmp_path / "Library/Application Support/Claude/claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "desde-claude": {"command": sys.executable, "args": [str(script)]}
                }
            }
        )
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    assert "1 conectores" in run("add-from-claude-desktop")


def test_sergio_serves_its_tools_to_the_official_sdk_client():
    anyio = pytest.importorskip("anyio")
    from mcp.client.stdio import stdio_client

    from mcp import ClientSession, StdioServerParameters

    sergio = Path(sys.executable).with_name("sergio")
    if not sergio.exists():
        pytest.skip("sergio is not installed in this environment")

    async def main() -> tuple:
        params = StdioServerParameters(
            command=str(sergio), args=["mcp", "serve", "--tools", "calculator"]
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("calculator", {"expression": "6*7"})
                return (
                    init.server_info.name,
                    [t.name for t in tools.tools],
                    result.content[0].text,
                )

    name, tools, text = anyio.run(main)
    assert name == "sergio" and tools == ["calculator"] and text.startswith("42")
