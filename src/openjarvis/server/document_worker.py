"""One disposable parser process with a CPU/memory budget on POSIX."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    from fastapi import HTTPException

    from openjarvis.server.upload_router import _parse_upload

    path = Path(sys.argv[1])
    try:
        text = _parse_upload(path.read_bytes(), path.suffix)
        print(json.dumps({"text": text}))
    except HTTPException as exc:
        print(json.dumps({"status": exc.status_code, "detail": exc.detail}))
    except Exception:
        print(json.dumps({"status": 400, "detail": "Document could not be parsed"}))


if __name__ == "__main__":
    main()


__all__ = ["main"]
