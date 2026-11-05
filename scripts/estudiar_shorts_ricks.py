"""Measure the verified Ricks Clips cohort at 30 fps, with optional local files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openjarvis.video_essay import escuela

SNAPSHOT = Path(__file__).with_name("ricks_shorts_2026-11-05.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--media", type=Path, help="Carpeta con videos nombrados por ID"
    )
    parser.add_argument(
        "--informe", type=Path, help="Ruta para guardar el JSON de resultados"
    )
    args = parser.parse_args()
    if args.media is not None and not args.media.is_dir():
        parser.error("--media debe ser una carpeta existente")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    result = escuela.run_all(
        ["shorts-animados"],
        on_step=lambda line: print(line, file=sys.stderr, flush=True),
        shorts_ids=snapshot["ids"],
        shorts_media=args.media,
    )
    result["lista_verificada"] = snapshot
    report = json.dumps(result, ensure_ascii=False, indent=2)
    if args.informe is not None:
        args.informe.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if result["cohortes"]["shorts-animados"]["perfil_actualizado"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
