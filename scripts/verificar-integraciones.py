#!/usr/bin/env python3
"""Read-only repository inventory. Presence is not full runtime verification."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
from pathlib import Path


def inventory(root: Path) -> dict:
    manifest = json.loads(
        (root / "docs/es/VERIFICACION-REPOS-2026-10-13.json").read_text(
            encoding="utf-8"
        )
    )
    rows = []
    for entry in manifest["repositories"]:
        missing = []
        for relative in entry["evidence_files"]:
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                missing.append(relative)
        rows.append(
            {
                "repository": entry["repository"],
                "representation": entry["representation"],
                "source_evidence_present": not missing,
                "missing_files": missing,
                "github_resolved_at_audit": entry["github_resolved"],
                "whole_repository_embedded": entry[
                    "whole_upstream_repository_embedded"
                ],
                "executable_detected_on_this_host": any(
                    shutil.which(binary) for binary in entry["binaries"]
                )
                if entry["binaries"]
                else None,
                "all_functions_runtime_verified": False,
            }
        )
    return {
        "host": platform.system(),
        "scope": "Solo este host y checkout; WSL no acredita las instalaciones de Windows.",
        "source_commit_audited": manifest["audited_source_commit"],
        "complete_equivalence_verified": False,
        "all_repositories_embedded_complete": all(
            row["whole_repository_embedded"] for row in rows
        ),
        "repositories": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="Imprimir el diagnóstico JSON."
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        result = inventory(root)
    except (OSError, ValueError, KeyError) as exc:
        print(f"No pude leer el inventario: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Host: {result['host']}. {result['scope']}")
        for row in result["repositories"]:
            evidence = "presente" if row["source_evidence_present"] else "FALTA"
            binary = row["executable_detected_on_this_host"]
            runtime = (
                "ejecutable detectado"
                if binary
                else ("ejecutable no detectado" if binary is False else "no comprobado")
            )
            print(
                f"{row['repository']}: {row['representation']} | evidencia local: {evidence} | {runtime}"
            )
        print("Repos completos incorporados: NO. Equivalencia completa acreditada: NO.")
        print("Detectar un ejecutable o un adaptador no verifica todas sus funciones.")
    return (
        1
        if any(not row["source_evidence_present"] for row in result["repositories"])
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
