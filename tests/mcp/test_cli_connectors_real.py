"""Real CLI processes and MCP pipes/HTTP, using disposable local fixtures."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.cli.mcp_cmd import mcp
from openjarvis.mcp.hub import ConnectorError, ConnectorHub
from openjarvis.mcp.local import local_environment
from openjarvis.server.mcp_routes import router


def result(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}], "isError": False}


def test_cli_calls_real_git_and_keeps_project_path_with_spaces(tmp_path):
    project = tmp_path / "daily project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / "notes.txt").write_text("daily work")
    hub = ConnectorHub(tmp_path / "hub", approver=lambda *_: True)
    c = hub.add_cli("Git", ["git"], cwd=str(project))
    sid = c["id"]
    assert hub.connect(sid)["server"]["status"] == "connected"
    assert hub.get(sid)["tools"][0]["permission"] == "ask"
    try:
        out = hub.call(sid, "run", {"arguments": ["status", "--porcelain"]})
        assert not out["isError"]
        assert "notes.txt" in json.loads(out["content"][0]["text"])["stdout"]
        hub.set_permission(sid, "run", "block")
        with pytest.raises(ConnectorError, match="no permite"):
            hub.call(sid, "run", {"arguments": ["clean", "-fd"]}, approved=True)
        assert (project / "notes.txt").exists()
        hub.set_permission(sid, "run", "ask")
        hub._approver = lambda *_: False
        with pytest.raises(ConnectorError, match="no aprobó"):
            hub.call(sid, "run", {"arguments": ["clean", "-fd"]})
        assert (project / "notes.txt").exists()
    finally:
        hub.disconnect(sid)


def test_cli_private_env_exit_codes_limits_and_no_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    hub = ConnectorHub(tmp_path / "hub")
    c = hub.add_cli(
        "Python",
        [sys.executable],
        cwd=str(tmp_path),
        env={"EXPLICIT_TOKEN": "fixture-only"},
    )
    sid = c["id"]
    hub.connect(sid)

    def run(code, *args, **options):
        return hub.call(
            sid, "run", {"arguments": ["-c", code, *args], **options}, approved=True
        )

    try:
        out = run(
            "import os,json,sys;print(json.dumps([os.getenv('OPENAI_API_KEY'),"
            "os.getenv('EXPLICIT_TOKEN'),sys.argv[1]]))",
            "; touch injected",
        )
        captured = json.loads(out["content"][0]["text"])
        assert json.loads(captured["stdout"]) == [
            None,
            "fixture-only",
            "; touch injected",
        ]
        assert not (tmp_path / "injected").exists()
        assert "fixture-only" not in (tmp_path / "hub/servers.json").read_text()
        assert "fixture-only" not in json.dumps(hub.list())
        assert run("import sys;sys.exit(7)")["isError"]
        assert run("import time;time.sleep(3)", timeout=0.1)["isError"]
        assert run("print('x'*100000)")["isError"] is False
        assert (
            json.loads(run("print('x'*100000)")["content"][0]["text"])["truncated"]
            is True
        )
        assert run("print('should not run')", timeout=float("nan"))["isError"]
    finally:
        hub.disconnect(sid)


def test_cli_api_and_command_line_use_the_same_hub(tmp_path, monkeypatch):
    hub = ConnectorHub(tmp_path / "hub")
    monkeypatch.setattr("openjarvis.server.mcp_routes.get_hub", lambda: hub)
    monkeypatch.setattr("openjarvis.cli.mcp_cmd._hub", lambda: hub)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as api:
        c = api.post(
            "/v1/mcp/servers",
            json={
                "kind": "cli",
                "name": "Git",
                "command": ["git"],
                "cwd": str(tmp_path),
            },
        ).json()["server"]
        sid = c["id"]
        assert api.post(f"/v1/mcp/servers/{sid}/connect").status_code == 200
        out = api.post(
            f"/v1/mcp/servers/{sid}/call",
            json={"tool": "run", "arguments": {"arguments": ["--version"]}},
        )
        assert "git version" in out.text and not out.json()["isError"]
        assert (
            api.post(
                "/v1/mcp/servers",
                json={
                    "kind": "cli",
                    "command": ["missing-sergio-binary"],
                    "cwd": str(tmp_path),
                },
            ).status_code
            == 400
        )
        assert (
            api.post(
                "/v1/mcp/servers",
                json={
                    "kind": "cli",
                    "command": ["git"],
                    "cwd": str(tmp_path / "missing"),
                },
            ).status_code
            == 400
        )
        assert (
            CliRunner()
            .invoke(
                mcp, ["add-cli", "--cwd", str(tmp_path), "Terminal Git", "--", "git"]
            )
            .exit_code
            == 0
        )
        for c in hub.list():
            hub.disconnect(c["id"])


def test_real_mcp_stdio_handshake_call_and_private_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    fixture = tmp_path / "mcp fixture.py"
    fixture.write_text("""import json,sys,os
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r: continue
 m=r['method']
 if m=='initialize':
  out={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},
       'serverInfo':{'name':'fixture','version':'1'}}
 elif m=='tools/list':
  out={'tools':[{'name':'echo','inputSchema':{'type':'object'},
                'annotations':{'readOnlyHint':True}}]}
 else:
  payload={'args':r['params']['arguments'],'leaked':os.getenv('OPENAI_API_KEY'),
           'explicit':os.getenv('EXPLICIT_TOKEN')}
  out={'content':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':out},ensure_ascii=False),flush=True)
""")
    hub = ConnectorHub(tmp_path / "hub")
    sid = hub.add_local(
        "Fixture",
        [sys.executable, str(fixture)],
        env={"EXPLICIT_TOKEN": "fixture-only"},
    )["id"]
    try:
        hub.connect(sid)
        out = hub.call(sid, "echo", {"path": "daily project/niño"})
        assert json.loads(out["content"][0]["text"]) == {
            "args": {"path": "daily project/niño"},
            "leaked": None,
            "explicit": "fixture-only",
        }
    finally:
        hub.disconnect(sid)


def test_real_mcp_streamable_http_initialize_discover_and_call(tmp_path, monkeypatch):
    for name in (
        "ALL_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "http_proxy",
        "https_proxy",
    ):
        monkeypatch.delenv(name, raising=False)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if "id" not in req:
                self.send_response(202)
                self.end_headers()
                return
            m = req["method"]
            if m == "initialize":
                out = {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "HTTP fixture", "version": "1"},
                }
            elif m == "tools/list":
                out = {
                    "tools": [
                        {
                            "name": "echo",
                            "inputSchema": {"type": "object"},
                            "annotations": {"readOnlyHint": True},
                        }
                    ]
                }
            else:
                out = result(req["params"]["arguments"])
            data = json.dumps(
                {"jsonrpc": "2.0", "id": req["id"], "result": out}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_DELETE(self):
            self.send_response(200)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    hub = ConnectorHub(tmp_path / "hub")
    sid = hub.add_remote("HTTP", f"http://127.0.0.1:{server.server_port}/mcp")["id"]
    try:
        hub.connect(sid)
        assert json.loads(
            hub.call(sid, "echo", {"hello": "daily work"})["content"][0]["text"]
        ) == {"hello": "daily work"}
    finally:
        hub.disconnect(sid)
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_no_implicit_proxy_or_provider_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private")
    monkeypatch.setenv("HTTPS_PROXY", "private")
    env = local_environment({"SELECTED_TOKEN": "allowed"})
    assert (
        env["SELECTED_TOKEN"] == "allowed"
        and "ANTHROPIC_API_KEY" not in env
        and "HTTPS_PROXY" not in env
    )
