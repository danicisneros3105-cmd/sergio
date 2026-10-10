"""Write Sergio's HTTP API description (OpenAPI 3) to docs/api/openapi.json.

    python scripts/export_openapi.py            # writes the file
    python scripts/export_openapi.py --check    # exits 1 if the file is stale

The app is built with a stand-in engine, so nothing is started and no model
is needed. Routes that only exist with optional extras appear when those
extras are installed; generate the committed file with ``--extra server``
and the dev extras.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "api" / "openapi.json"


def build_spec() -> Dict[str, Any]:
    from openjarvis import __version__
    from openjarvis.server.app import create_app

    engine = MagicMock()
    engine.engine_id = "local"
    engine.health.return_value = True
    engine.list_models.return_value = []
    app = create_app(engine, "", memory_service=MagicMock())
    app.title = "Sergio API"
    # The release only, so the file doesn't change with every commit.
    app.version = __version__.split(".dev")[0].split("+")[0]
    app.description = (
        "La API local de Sergio (fork de OpenJarvis, Apache 2.0). Compatible con "
        "OpenAI en /v1/chat/completions, /v1/models y /v1/embeddings. Escucha en "
        "http://127.0.0.1:8000 por defecto; si el servidor se inició con una "
        "clave, envíela como 'Authorization: Bearer <clave>'."
    )
    app.openapi_schema = None
    return app.openapi()


def render(spec: Dict[str, Any]) -> str:
    return json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    text = render(build_spec())
    if args.check:
        current = args.out.read_text("utf-8") if args.out.exists() else ""
        if current != text:
            print(f"{args.out} is stale: run python scripts/export_openapi.py")
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, "utf-8")
    spec = json.loads(text)
    print(f"{args.out}: {len(spec['paths'])} paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
