"""Bound upload bodies before multipart parsing and limit concurrent batches."""

from __future__ import annotations

import asyncio
import tempfile

from starlette.responses import JSONResponse


class UploadLimitsMiddleware:
    def __init__(
        self, app, *, max_bytes=65 * 1024 * 1024, max_concurrent=2, receive_timeout=30
    ):
        self.app = app
        self.max_bytes = max_bytes
        self.receive_timeout = receive_timeout
        self.slots = asyncio.Semaphore(max_concurrent)

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not (
            path.startswith("/v1/connectors/upload/") or path.rstrip("/") == "/v1/personal/videos/galeria"
        ):
            await self.app(scope, receive, send)
            return

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(
                scope, receive, send
            )

        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            await reject(400, "Invalid Content-Length")
            return
        if declared < 0 or declared > self.max_bytes:
            await reject(413, "Upload body is too large")
            return
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            await reject(429, "Uploads busy; retry shortly")
            return
        try:
            with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as body:
                total = 0
                timeout = max(self.receive_timeout, 180) if path.rstrip("/") == "/v1/personal/videos/galeria" else self.receive_timeout
                deadline = asyncio.get_running_loop().time() + timeout
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        await reject(408, "Upload timed out")
                        return
                    try:
                        message = await asyncio.wait_for(receive(), remaining)
                    except asyncio.TimeoutError:
                        await reject(408, "Upload timed out")
                        return
                    if message["type"] == "http.disconnect":
                        return
                    data = message.get("body", b"")
                    total += len(data)
                    if total > self.max_bytes:
                        await reject(413, "Upload body is too large")
                        return
                    body.write(data)
                    if not message.get("more_body", False):
                        break
                body.seek(0)
                finished = False

                async def replay():
                    nonlocal finished
                    if finished:
                        return await receive()
                    data = body.read(64 * 1024)
                    more = body.tell() < total
                    finished = not more
                    return {"type": "http.request", "body": data, "more_body": more}

                await self.app(scope, replay, send)
        finally:
            self.slots.release()


__all__ = ["UploadLimitsMiddleware"]
