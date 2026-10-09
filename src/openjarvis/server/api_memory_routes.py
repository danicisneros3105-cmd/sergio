"""Memory endpoints (``/v1/memory``): store, search, stats, configuration
and indexing of local files.

Split out of ``api_routes.py``, which owns the router; its names are looked
up on that module, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request

import openjarvis.server.api_routes as _api


def _get_memory_backend(request: Request):
    """Return the app-level memory backend, falling back to a fresh SQLiteMemory.

    Without the native ``openjarvis_rust`` extension the Python twin of the
    backend is used. Raises ``HTTPException(503)`` with an actionable message
    when no backend can be built for an environment reason (no FTS5 in
    Python's SQLite). This is deliberately distinct from a benign "memory not
    configured" case (which returns ``None``): it must fail loudly, never
    silently degrade (#502).
    """
    backend = getattr(request.app.state, "memory_backend", None)
    if backend is None:
        from openjarvis.tools.storage._stubs import MemoryBackendUnavailable

        try:
            from openjarvis.tools.storage.sqlite import SQLiteMemory

            backend = SQLiteMemory()
        except MemoryBackendUnavailable as exc:
            # No usable backend in this environment — surface a loud, actionable error
            # rather than a misleading "no backend" / silent no-op.
            _api.logger.error("%s", exc)
            raise _api.HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception:
            # Memory is genuinely unconfigured for a benign reason — preserve
            # the existing graceful "no backend" behaviour.
            return None
    return backend


@_api.memory_router.post("/store")
def memory_store(req: _api.MemoryStoreRequest, request: Request):
    """Store content in memory."""
    backend = _api._get_memory_backend(request)
    if backend is None:
        # Memory is intentionally disabled; report it honestly instead of a
        # 200 that silently discards the write (#502).
        raise _api.HTTPException(status_code=503, detail="Memory is not configured")
    try:
        backend.store(req.content, metadata=req.metadata or {})
        return {"status": "stored"}
    except Exception as exc:
        raise _api.HTTPException(status_code=500, detail=str(exc))


@_api.memory_router.post("/search")
def memory_search(req: _api.MemorySearchRequest, request: Request):
    """Search memory for relevant content."""
    backend = _api._get_memory_backend(request)
    if backend is None:
        return {"results": []}
    try:
        results = backend.retrieve(req.query, top_k=req.top_k)
        items = [
            {
                "content": r.content,
                "score": getattr(r, "score", 0.0),
                "metadata": getattr(r, "metadata", {}),
            }
            for r in results
        ]
        return {"results": items}
    except Exception as exc:
        raise _api.HTTPException(status_code=500, detail=str(exc))


@_api.memory_router.get("/stats")
def memory_stats(request: Request):
    """Get memory backend statistics."""
    backend = _api._get_memory_backend(request)
    if backend is None:
        return {"entries": 0, "backend": "none", "status": "not_configured"}
    try:
        return {
            "entries": backend.count(),
            "backend": getattr(backend, "backend_id", "unknown"),
        }
    except Exception as exc:
        raise _api.HTTPException(status_code=500, detail=str(exc))


@_api.memory_router.get("/config")
async def memory_config(request: Request):
    """Return current memory configuration.

    Reports memory as *unavailable* (rather than falsely claiming
    ``backend_type: sqlite``) when no backend can be built in this
    environment, so the UI can show the real cause instead of a
    healthy-looking config that backs a silent no-op (#502).
    """
    try:
        config = getattr(request.app.state, "config", None)
        if config is None:
            from openjarvis.core.config import load_config

            config = load_config()
        backend = getattr(request.app.state, "memory_backend", None)
        available = True
        detail: Optional[str] = None
        if backend is None:
            from openjarvis.tools.storage._stubs import MemoryBackendUnavailable

            try:
                from openjarvis.tools.storage.sqlite import SQLiteMemory

                backend = SQLiteMemory()
            except MemoryBackendUnavailable as exc:
                available = False
                detail = str(exc)
            except Exception:
                # Benign: cannot construct a probe backend here, but the
                # configured default is still what would be used.
                pass
        return {
            "backend_type": (
                backend.backend_id
                if backend is not None
                else config.memory.default_backend
            ),
            "available": available,
            "detail": detail,
            "context_top_k": config.memory.context_top_k,
            "context_min_score": config.memory.context_min_score,
            "context_max_tokens": config.memory.context_max_tokens,
            "context_from_memory": config.agent.context_from_memory,
        }
    except Exception as exc:
        raise _api.HTTPException(status_code=500, detail=str(exc))


@_api.memory_router.post("/index")
def memory_index(req: _api.MemoryIndexRequest, request: Request):
    """Index files from a path into memory."""
    try:
        import os
        from pathlib import Path

        from openjarvis.security.file_policy import is_sensitive_file
        from openjarvis.tools.storage.ingest import ingest_path

        target = Path(req.path).expanduser().resolve()
        if not target.exists():
            raise _api.HTTPException(
                status_code=404, detail=f"Path not found: {req.path}"
            )

        # Sandbox: when workspace roots are configured via OPENJARVIS_WORKSPACE
        # (os.pathsep-separated), only allow indexing inside them. This endpoint
        # must not become an arbitrary-filesystem read primitive over the API.
        workspace = os.environ.get("OPENJARVIS_WORKSPACE", "").strip()
        if workspace:
            roots = [
                Path(d).expanduser().resolve()
                for d in workspace.split(os.pathsep)
                if d.strip()
            ]
            if not any(target == root or root in target.parents for root in roots):
                raise _api.HTTPException(
                    status_code=403,
                    detail="Path is outside the allowed workspace directories.",
                )
        # Never ingest sensitive files (.env, private keys, credentials, ...).
        if target.is_file() and is_sensitive_file(target):
            raise _api.HTTPException(
                status_code=403, detail="Refusing to index a sensitive file."
            )

        backend = _api._get_memory_backend(request)
        if backend is None:
            raise _api.HTTPException(status_code=503, detail="Memory is not configured")

        chunks = ingest_path(target)
        stored = 0
        for chunk in chunks:
            metadata = {"source": getattr(chunk, "source", str(target))}
            if hasattr(chunk, "metadata") and chunk.metadata:
                metadata.update(chunk.metadata)
            backend.store(chunk.content, metadata=metadata)
            stored += 1

        result = {"status": "indexed", "chunks_indexed": stored}
        if stored == 0:
            # "indexed" must never silently mean "stored nothing". Surface why
            # so a folder of short notes doesn't look like a successful no-op
            # (#502 follow-up).
            result["note"] = (
                "no content was indexed — the path contained no readable "
                "documents with indexable text"
            )
        return result
    except _api.HTTPException:
        raise
    except Exception as exc:
        raise _api.HTTPException(status_code=500, detail=str(exc))


__all__ = [
    "_get_memory_backend",
    "memory_store",
    "memory_search",
    "memory_stats",
    "memory_config",
    "memory_index",
]
