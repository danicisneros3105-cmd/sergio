"""Check the built Sergio client in real browser engines, with a synthetic API."""

from __future__ import annotations

import argparse
import functools
import json
import struct
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

TOKEN = "sg_release_smoke_synthetic"
ACCOUNT = {"id": "1111111111111111", "role": "dueño", "name": "QA"}
GOAL = "Comprobar el resultado de la prueba"
PROOF = "Texto verificado en la página de prueba."
DEVICE_PROFILES = {
    "chromium": ("Desktop Chrome", "Pixel 7"),
    "webkit": ("Desktop Safari", "iPhone 15", "iPad (gen 7)"),
}


def verify_build(root: Path) -> None:
    manifest = json.loads((root / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert (manifest["display"], manifest["start_url"], manifest["scope"]) == (
        "standalone",
        "/",
        "/",
    )
    assert (root / "sw.js").stat().st_size > 0
    for size in (192, 512):
        icon = next(i for i in manifest["icons"] if i["sizes"] == f"{size}x{size}")
        path = urlsplit(icon["src"]).path
        assert path == f"pwa-{size}x{size}.png"
        header = (root / path).read_bytes()[:24]
        assert header.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", header[16:24]) == (size, size)
    assert "manifest.webmanifest" in (root / "index.html").read_text(encoding="utf-8")


class SmokeHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def signed_in(self):
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/v1/cuentas/estado":
            self.send_json(
                {
                    "accounts": 1,
                    "local": False,
                    "me": ACCOUNT if self.signed_in() else None,
                }
            )
        elif path.startswith("/v1/cowork"):
            if not self.signed_in():
                self.send_json({"detail": "Falta sesión"}, 401)
                return
            elapsed = time.monotonic() - self.server.started_at
            finished = elapsed >= 1.5
            run = {
                "id": "smoke",
                "title": GOAL,
                "goal": GOAL,
                "status": "done" if finished else "running",
                "summary": PROOF if finished else "",
                "steps": [],
                "waiting": [],
                "notes": [],
                "actions_used": 0,
                "max_actions": 50,
                "progress": int(finished),
            }
            if path == "/v1/cowork":
                self.send_json({"runs": [run] if self.server.started_at else []})
            elif path == "/v1/cowork/smoke/events":
                body = (
                    f"data: {json.dumps({'type': 'snapshot', 'run': run})}\n\n".encode()
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json(run)
        elif path == "/health":
            self.send_json({"status": "ok"})
        elif path.startswith(("/v1/", "/api/")):
            self.send_json({"detail": "No aplica a esta prueba"}, 404)
        else:
            if path in ("/", "/entrar", "/cowork"):
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if self.path == "/v1/cuentas/entrar" and body.get("email") == "qa@example.test":
            self.send_json({"status": "dentro", "token": TOKEN})
        elif (
            self.path == "/v1/cowork" and self.signed_in() and body.get("goal") == GOAL
        ):
            self.server.started_at = time.monotonic()
            self.send_json(
                {
                    "id": "smoke",
                    "title": GOAL,
                    "goal": GOAL,
                    "status": "running",
                    "steps": [],
                    "waiting": [],
                    "notes": [],
                    "actions_used": 0,
                    "max_actions": 50,
                    "progress": 0,
                }
            )
        else:
            self.send_json({"detail": "No aplica a esta prueba"}, 404)


def sign_in(page, origin: str) -> None:
    page.goto(origin + "/entrar")
    page.locator("input[type=email]").fill("qa@example.test")
    page.locator("input[autocomplete=current-password]").fill(
        "clave-sintetica-de-prueba"
    )
    page.get_by_role("button", name="Entrar", exact=True).click()
    page.wait_for_url(origin + "/")
    page.goto(origin + "/cowork")
    page.get_by_role("textbox", name="Describa el resultado que quiere").wait_for()


def smoke(root: Path, engine: str) -> None:
    from playwright.sync_api import sync_playwright

    with ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(SmokeHandler, directory=str(root))
    ) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = getattr(playwright, engine).launch()
                for profile in DEVICE_PROFILES[engine]:
                    server.started_at = 0.0
                    context = browser.new_context(**playwright.devices[profile])
                    try:
                        context.route(
                            "**/*",
                            lambda route: (
                                route.continue_()
                                if route.request.url.startswith(origin + "/")
                                else route.abort()
                            ),
                        )
                        context.add_init_script(
                            "localStorage.setItem('sergio-tour-v1', '1')"
                        )
                        page = context.new_page()
                        sign_in(page, origin)
                        page.wait_for_function(
                            """async () => isSecureContext &&
                            Boolean(await navigator.serviceWorker.getRegistration('/'))"""
                        )
                        if profile.startswith(("iPhone", "iPad")):
                            page.get_by_text("Para instalarlo:", exact=False).wait_for()
                        page.get_by_role(
                            "textbox", name="Describa el resultado que quiere"
                        ).fill(GOAL)
                        with page.expect_response(
                            lambda r: (
                                r.url == origin + "/v1/cowork"
                                and r.request.method == "POST"
                            )
                        ) as response:
                            page.get_by_role(
                                "button", name="Enviar", exact=True
                            ).click()
                        assert response.value.ok
                        page.close()
                        resumed = context.new_page()
                        sign_in(resumed, origin)
                        resumed.get_by_text(GOAL, exact=True).first.click()
                        resumed.get_by_text(PROOF, exact=True).first.wait_for()
                        print(
                            f"OK: {engine}, {profile}: session, worker and task reopened"
                        )
                    finally:
                        context.close()
                browser.close()
        finally:
            server.shutdown()
            thread.join()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--engine", choices=DEVICE_PROFILES)
    args = parser.parse_args()
    verify_build(args.build)
    print("OK: production PWA manifest, worker and icon sizes")
    if args.engine:
        smoke(args.build, args.engine)


if __name__ == "__main__":
    main()
