"""Tests for security middleware -- HTTP security headers."""

from __future__ import annotations

from unittest.mock import patch

from openjarvis.server.middleware import SECURITY_HEADERS, create_security_middleware


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_headers_dict(self) -> None:
        """Verify SECURITY_HEADERS has all expected keys."""
        expected_keys = {
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
            "Referrer-Policy",
            "Permissions-Policy",
            "Content-Security-Policy",
        }
        assert set(SECURITY_HEADERS.keys()) == expected_keys

    def test_create_middleware_without_starlette(self) -> None:
        """When starlette is not available, returns None."""
        import importlib

        import openjarvis.server.middleware as mod

        blocked = {
            "starlette": None,
            "starlette.middleware": None,
            "starlette.middleware.base": None,
            "starlette.requests": None,
            "starlette.responses": None,
        }
        with patch.dict("sys.modules", blocked):
            importlib.reload(mod)
            result = mod.create_security_middleware()
            assert result is None
            # Reload again to restore normal state
            importlib.reload(mod)

    def test_create_middleware_with_starlette(self) -> None:
        """When starlette is available, returns a class."""
        middleware_cls = create_security_middleware()
        if middleware_cls is None:
            # starlette not installed -- skip
            import pytest

            pytest.skip("starlette not available")
        assert middleware_cls is not None
        assert callable(middleware_cls)

    def test_middleware_adds_headers(self) -> None:
        """Middleware adds all security headers to responses."""
        import pytest

        fastapi = pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        app = fastapi.FastAPI()

        middleware_cls = create_security_middleware()
        assert middleware_cls is not None
        app.add_middleware(middleware_cls)

        @app.get("/test")
        def test_endpoint() -> dict:
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200

        for header_name, header_value in SECURITY_HEADERS.items():
            assert resp.headers.get(header_name) == header_value, (
                f"Missing or wrong header: {header_name}"
            )

    def test_middleware_skips_options(self) -> None:
        """OPTIONS requests pass through without security headers."""
        import pytest

        fastapi = pytest.importorskip("fastapi")
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.testclient import TestClient

        app = fastapi.FastAPI()

        # Add CORS first, then security (reverse execution order)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        middleware_cls = create_security_middleware()
        assert middleware_cls is not None
        app.add_middleware(middleware_cls)

        @app.post("/test")
        def test_endpoint() -> dict:
            return {"ok": True}

        client = TestClient(app)
        resp = client.options(
            "/test",
            headers={
                "Origin": "https://tauri.localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers
        # Security headers should NOT be present on preflight
        assert "X-Frame-Options" not in resp.headers


class TestSpeechHeaders:
    """The security headers must not block the web UI's own speech features."""

    def test_csp_allows_blob_media(self):
        """Synthesized speech reaches the player as a blob URL."""
        csp = SECURITY_HEADERS["Content-Security-Policy"]
        assert "media-src 'self' blob:" in csp

    def test_microphone_allowed_for_same_origin(self):
        """An empty allowlist would block the chat UI's own voice input."""
        policy = SECURITY_HEADERS["Permissions-Policy"]
        assert "microphone=(self)" in policy
        assert "microphone=()" not in policy

    def test_camera_same_origin_only_and_geolocation_blocked(self):
        """The Faces page uses the camera from this origin; nothing else may."""
        policy = SECURITY_HEADERS["Permissions-Policy"]
        assert "camera=(self)" in policy
        assert "camera=*" not in policy
        assert "geolocation=()" in policy


def test_csp_allows_only_local_extension_frames_and_inline_assets():
    from openjarvis.server.middleware import content_security_policy

    csp = content_security_policy((7070, 4173))
    assert "frame-src 'self' http://127.0.0.1:7070 http://localhost:7070" in csp
    assert "http://127.0.0.1:4173" in csp and "https://" not in csp
    assert "font-src 'self' data:" in csp and "img-src 'self' data: blob:" in csp
    assert "media-src 'self' blob:" in csp
    assert "default-src 'self';" in csp
    assert "script-src 'self';" in csp
    assert "unsafe-eval" not in csp
    assert "object-src 'none';" in csp and "form-action 'self'" in csp


def test_answers_travel_compressed_and_hashed_files_are_kept(tmp_path, monkeypatch):
    """The app's code goes gzipped; a file named by its hash is cached for good,
    an older name resolved to the new file never is."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.middleware.gzip import GZipMiddleware

    from openjarvis.server.app import _NoCacheStaticFiles

    (tmp_path / "index-abc12345.js").write_text("console.log('sergio');" * 400)
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.mount("/assets", _NoCacheStaticFiles(directory=tmp_path), name="a")
    client = TestClient(app)
    fresh = client.get("/assets/index-abc12345.js", headers={"Accept-Encoding": "gzip"})
    assert fresh.status_code == 200
    assert fresh.headers["content-encoding"] == "gzip"
    assert "immutable" in fresh.headers["cache-control"]
    stale = client.get("/assets/index-old99999.js")
    assert stale.status_code == 200 and "no-store" in stale.headers["cache-control"]
