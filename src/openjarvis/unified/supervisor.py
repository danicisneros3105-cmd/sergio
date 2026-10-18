"""Start, stop and inspect the bundled extensions as background services.

Each extension runs as its own process (OpenClacky is Ruby, the globe is a
Node/Vite app), detached into its own process group so a single ``stop``
tears down the whole tree. Pid files and logs live in
``~/.openjarvis/extensions/``.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from openjarvis.unified.model_bridge import ModelBridgeError, clacky_env
from openjarvis.unified.paths import extension_dir, state_dir

_IS_WINDOWS = sys.platform == "win32"

# Creator's programs that run here and show inside Sergio's web (installed
# by scripts/instalar-programas.sh into ~/.openjarvis/apps).
OPENDESIGN_PORT = 8790  # its editor (vite preview, proxies /api)
OPENDESIGN_API_PORT = 8787  # its API (wrangler dev: Hono + local SQLite)
VSCODIUM_PORT = 8791
CREATOR_APPS = ("opendesign", "vscodium")


@dataclass
class Service:
    """One extension process."""

    name: str
    title: str
    port: int
    cwd: Path | None
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    install: list[str] = field(default_factory=list)
    # Returns True when dependencies must be installed before starting.
    needs_install: Callable[[], bool] = lambda: False
    problem: str = ""  # Why it cannot run (empty when it can)
    listens: bool = True  # False for clients such as the tunnel (no local port)
    display_url: str = ""

    @property
    def url(self) -> str:
        return self.display_url or f"http://127.0.0.1:{self.port}"


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if _IS_WINDOWS:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _start_token(pid: int) -> str | None:
    """Kernel start time of *pid* (Linux), to detect a recycled pid."""
    from openjarvis.core.utils import _proc_pid_namespace_matches

    if not _proc_pid_namespace_matches():
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # Field 22 (starttime) comes after the parenthesised command name.
    fields = stat.rsplit(")", 1)[-1].split()
    return fields[19] if len(fields) > 19 else None


def tool_dirs(home: Path | None = None) -> list[str]:
    """Folders where Node/Ruby usually live but a service PATH may miss.

    The installer puts Node 24 under mise; nvm, volta and /usr/local are
    covered too, newest Node first.
    """
    home = home or Path.home()
    dirs = [
        home / ".local" / "share" / "mise" / "shims",
        home / ".local" / "bin",
        home / ".volta" / "bin",
        Path("/usr/local/bin"),
    ]
    for pattern in (
        ".local/share/mise/installs/node/*/bin",
        ".nvm/versions/node/*/bin",
    ):
        dirs += sorted(home.glob(pattern), reverse=True)
    return [str(d) for d in dirs if d.is_dir()]


def find_tool(name: str) -> str | None:
    """``shutil.which`` that also looks in :func:`tool_dirs`."""
    path = os.pathsep.join([os.environ.get("PATH", ""), *tool_dirs()])
    return shutil.which(name, path=path)


class Supervisor:
    """Manage the OpenClacky and globe services for one OpenJarvis config."""

    def __init__(
        self,
        config: Any,
        *,
        which: Callable[[str], str | None] = find_tool,
        environ: dict[str, str] | None = None,
        ui_ports: tuple[int, ...] = (),
        server_port: int | None = None,
    ) -> None:
        self._config = config
        self._which = which
        # Ports the Sergio UI is served on (allowed to embed the globe).
        self._ui_ports = ui_ports
        # Port of the Sergio API server (target of the public tunnel).
        self._server_port = server_port
        self._environ = dict(os.environ if environ is None else environ)
        self._state = state_dir()

    # ------------------------------------------------------------------
    # Service definitions
    # ------------------------------------------------------------------

    def services(self) -> list[Service]:
        ext = self._config.extensions
        out: list[Service] = []
        if ext.clacky.enabled:
            out.append(self._clacky(ext.clacky))
        if ext.globe.enabled:
            out.append(self._globe(ext.globe))
        tunnel = getattr(self._config, "tunnel", None)
        if tunnel is not None and tunnel.provider:
            out.append(self._tunnel(tunnel))
        return out

    def creator_services(self) -> list[Service]:
        """Creator's programs: started on demand from the web, never at boot."""
        return [self._opendesign(), self._vscodium()]

    @staticmethod
    def apps_dir() -> Path:
        from openjarvis.core.paths import get_config_dir

        return get_config_dir() / "apps"

    def _node_path(self, tool: str) -> str:
        node_dir = str(Path(tool).resolve().parent)
        return os.pathsep.join([node_dir, self._environ.get("PATH", ""), *tool_dirs()])

    def _opendesign(self) -> Service:
        """OpenDesign (MIT): the Canva-like editor, its API and its editor in
        one process group so a single stop ends both."""
        cwd = self.apps_dir() / "opendesign"
        svc = Service("opendesign", "OpenDesign", OPENDESIGN_PORT, cwd)
        if not (cwd / "dist" / "index.html").is_file():
            svc.problem = "OpenDesign no está instalado (se instala al actualizar)"
            return svc
        npx = self._which("npx")
        if npx is None:
            svc.problem = "Falta Node.js (npx) para OpenDesign"
            return svc
        svc.env = {"PATH": self._node_path(npx), "WRANGLER_SEND_METRICS": "false"}
        tool = shlex.quote(npx)
        # The editor proxies /api to the API: it only opens its port once the
        # API answers, so "running" means both are ready.
        wait_api = (
            "for _ in $(seq 240); do "
            f"(exec 3<>/dev/tcp/127.0.0.1/{OPENDESIGN_API_PORT}) 2>/dev/null && break; "
            "sleep 0.5; done"
        )
        svc.command = [
            "bash",
            "-c",
            f"{tool} wrangler dev --port {OPENDESIGN_API_PORT} --ip 127.0.0.1 & "
            f"{wait_api}; "
            f"exec {tool} vite preview --port {OPENDESIGN_PORT} --host 127.0.0.1 --strictPort",
        ]
        return svc

    def vscodium_token(self) -> str:
        """The VSCodium web server's connection token (created once, private)."""
        path = self._state / "vscodium.token"
        try:
            token = path.read_text().strip()
        except OSError:
            token = ""
        if not token:
            token = secrets.token_urlsafe(24)
            path.write_text(token)
            path.chmod(0o600)
        return token

    def _vscodium(self) -> Service:
        """VSCodium in the browser (its official reh-web server)."""
        cwd = self.apps_dir() / "vscodium-web"
        svc = Service("vscodium", "VSCodium", VSCODIUM_PORT, cwd)
        server = cwd / "bin" / "codium-server"
        if not server.is_file():
            svc.problem = "VSCodium web no está instalado (se instala al actualizar)"
            return svc
        self.vscodium_token()
        from openjarvis.creator.studio import projects_root

        svc.command = [
            str(server),
            "--host",
            "127.0.0.1",
            "--port",
            str(VSCODIUM_PORT),
            "--connection-token-file",
            str(self._state / "vscodium.token"),
            "--accept-server-license-terms",
            "--default-folder",
            str(projects_root()),
        ]
        return svc

    def server_port(self) -> int:
        """The API port actually in use (gui/service override, then config)."""
        if self._server_port:
            return int(self._server_port)
        env = self._environ.get("SERGIO_SERVER_PORT", "")
        if env.isdigit():
            return int(env)
        return int(getattr(self._config.server, "port", 8000))

    def _tunnel(self, cfg: Any) -> Service:
        """Public HTTPS tunnel so Twilio/WhatsApp can reach the local server."""
        port = self.server_port()
        svc = Service(
            "tunnel",
            "Public tunnel (calls/WhatsApp)",
            port,
            Path.home(),
            listens=False,
            display_url=getattr(self._config.phone, "public_url", "") or "",
        )
        if cfg.provider == "ngrok":
            ngrok = self._which("ngrok")
            if ngrok is None:
                svc.problem = "ngrok is not installed (run the installer)"
            elif not self._environ.get("NGROK_AUTHTOKEN"):
                svc.problem = "NGROK_AUTHTOKEN missing in ~/.openjarvis/sergio.env"
            elif not cfg.domain:
                svc.problem = "set [tunnel] domain to your free ngrok static domain"
            else:
                svc.command = [ngrok, "http", f"--url={cfg.domain}", str(port)]
                svc.display_url = svc.display_url or f"https://{cfg.domain}"
        elif cfg.provider == "cloudflare":
            cloudflared = self._which("cloudflared")
            if cloudflared is None:
                svc.problem = "cloudflared is not installed"
            elif not self._environ.get("CLOUDFLARE_TUNNEL_TOKEN"):
                svc.problem = (
                    "CLOUDFLARE_TUNNEL_TOKEN missing in ~/.openjarvis/sergio.env"
                )
            else:
                svc.command = [cloudflared, "tunnel", "--no-autoupdate", "run"]
                svc.env = {"TUNNEL_TOKEN": self._environ["CLOUDFLARE_TUNNEL_TOKEN"]}
        else:
            svc.problem = (
                f"unknown tunnel provider '{cfg.provider}' (ngrok or cloudflare)"
            )
        return svc

    def _clacky(self, cfg: Any) -> Service:
        svc = Service(
            "clacky", "Agente de código", cfg.port, extension_dir("clacky", cfg.path)
        )
        if svc.cwd is None:
            svc.problem = "Falta extensions/clacky en esta instalación"
            return svc
        bundle = self._which("bundle")
        if self._which("ruby") is None or bundle is None:
            svc.problem = "Hacen falta Ruby 3.1 o más y Bundler (ejecute el instalador)"
            return svc
        try:
            svc.env = clacky_env(self._config, self._environ)
        except ModelBridgeError as exc:
            svc.problem = str(exc)
            return svc
        svc.install = [bundle, "install"]
        cwd = svc.cwd
        svc.needs_install = lambda: (
            subprocess.run(
                [bundle, "check"], cwd=cwd, capture_output=True, check=False
            ).returncode
            != 0
        )
        svc.command = [
            bundle,
            "exec",
            "ruby",
            "bin/clacky",
            "server",
            "--port",
            str(cfg.port),
            "--strict-port",
        ]
        return svc

    def _globe(self, cfg: Any) -> Service:
        svc = Service("globe", "Globo", cfg.port, extension_dir("globe", cfg.path))
        if svc.cwd is None:
            svc.problem = "Falta extensions/globe en esta instalación"
            return svc
        npm = self._which("npm") or self._which("npm.cmd")
        if npm is None:
            svc.problem = "Hacen falta Node.js 24 o más y npm (ejecute el instalador)"
            return svc
        # Let the OpenJarvis UI (Vite dev server or the API's static build)
        # embed the globe; the globe denies all other embedders.
        ui_ports = sorted({5173, self.server_port(), *self._ui_ports})
        # npm runs `node` from its own folder: make sure the globe sees it.
        node_dir = str(Path(npm).resolve().parent)
        path = os.pathsep.join([node_dir, self._environ.get("PATH", ""), *tool_dirs()])
        svc.env = {
            "PATH": path,
            "GLOBE_FRAME_ANCESTORS": " ".join(
                f"http://{host}:{port}"
                for port in ui_ports
                for host in ("127.0.0.1", "localhost")
            ),
        }
        svc.install = [npm, "ci"]
        modules = svc.cwd / "node_modules"
        svc.needs_install = lambda: not modules.is_dir()
        svc.command = [
            npm,
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(cfg.port),
            "--strictPort",
        ]
        return svc

    def get(self, name: str) -> Service:
        for svc in [*self.services(), *self.creator_services()]:
            if svc.name == name:
                return svc
        raise KeyError(f"Extension '{name}' is disabled or unknown")

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    def _pid_file(self, name: str) -> Path:
        return self._state / f"{name}.pid"

    def log_file(self, name: str) -> Path:
        return self._state / f"{name}.log"

    def _write_pid(self, name: str, pid: int) -> None:
        record = {"pid": pid, "start": _start_token(pid)}
        self._pid_file(name).write_text(json.dumps(record))

    def _pid(self, name: str) -> int:
        """Pid of our own process for *name*, or 0.

        After a reboot the saved pid may belong to an unrelated program;
        the recorded start time (Linux) rules that out, so ``stop`` never
        signals a process this supervisor did not start.
        """
        try:
            raw = self._pid_file(name).read_text().strip()
            record = json.loads(raw) if raw.startswith("{") else {"pid": int(raw)}
            pid = int(record.get("pid", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            return 0
        if not _pid_alive(pid):
            return 0
        expected = record.get("start")
        if expected is not None and _start_token(pid) != expected:
            return 0
        return pid

    def running(self, svc: Service) -> bool:
        return self._pid(svc.name) > 0 and (not svc.listens or port_open(svc.port))

    def start(self, svc: Service, *, wait: float = 60.0) -> str:
        """Start *svc*; return a short human-readable outcome."""
        if svc.problem:
            return f"skipped: {svc.problem}"
        if self.running(svc):
            return f"already running at {svc.url}"
        if svc.listens and port_open(svc.port):
            return f"port {svc.port} is busy (another program uses it)"
        env = {**self._environ, **svc.env}
        kwargs: dict[str, Any] = {}
        if _IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        # The child keeps its own copy of the log descriptor; ours is closed.
        with self.log_file(svc.name).open("ab") as log:
            if svc.needs_install():
                done = subprocess.run(
                    svc.install,
                    cwd=svc.cwd,
                    env=env,
                    stdout=log,
                    stderr=log,
                    check=False,
                )
                if done.returncode != 0:
                    return f"dependency install failed, see {self.log_file(svc.name)}"
            proc = subprocess.Popen(
                svc.command,
                cwd=svc.cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
        self._write_pid(svc.name, proc.pid)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                self._pid_file(svc.name).unlink(missing_ok=True)
                return f"exited early, see {self.log_file(svc.name)}"
            if svc.listens and port_open(svc.port):
                return f"running at {svc.url}"
            if not svc.listens and time.monotonic() > deadline - wait + 5:
                return f"running at {svc.url}"  # still alive after 5 s
            time.sleep(0.5)
        return f"started but not answering yet, see {self.log_file(svc.name)}"

    def stop(self, name: str) -> bool:
        pid = self._pid(name)
        self._pid_file(name).unlink(missing_ok=True)
        if pid <= 0:
            return False
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True
            )
            return True
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return False
        for _ in range(20):
            if not _pid_alive(pid):
                break
            time.sleep(0.25)
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return True

    def start_all(self) -> dict[str, str]:
        return {svc.name: self.start(svc) for svc in self.services()}

    def stop_all(self) -> dict[str, bool]:
        names = ("clacky", "globe", "tunnel", *CREATOR_APPS)
        return {name: self.stop(name) for name in names}

    def status(self, creator: bool = False) -> list[dict[str, Any]]:
        rows = []
        for svc in [*self.services(), *(self.creator_services() if creator else [])]:
            rows.append(
                {
                    "name": svc.name,
                    "title": svc.title,
                    "url": svc.url,
                    "running": self.running(svc),
                    "available": not svc.problem,
                    "problem": svc.problem,
                }
            )
        return rows


__all__ = [
    "find_tool",
    "port_open",
    "Service",
    "Supervisor",
    "tool_dirs",
]
