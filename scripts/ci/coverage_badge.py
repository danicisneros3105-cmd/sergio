"""Turn coverage.xml into a badge (SVG + shields.io JSON) and a summary.

Usage: python scripts/ci/coverage_badge.py coverage.xml OUT_DIR

Prints a Markdown summary (overall %, the ten least-covered big modules)
for $GITHUB_STEP_SUMMARY and writes OUT_DIR/coverage.svg and
OUT_DIR/coverage.json. The README shows the SVG from the "badges" branch.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="104" height="20" role="img" aria-label="coverage: {pct}%">
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<clipPath id="r"><rect width="104" height="20" rx="3" fill="#fff"/></clipPath>
<g clip-path="url(#r)"><rect width="61" height="20" fill="#555"/><rect x="61" width="43" height="20" fill="{color}"/><rect width="104" height="20" fill="url(#s)"/></g>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="110">
<text x="315" y="140" transform="scale(.1)">coverage</text><text x="815" y="140" transform="scale(.1)">{pct}%</text></g>
</svg>
"""


def color_for(pct: float) -> str:
    for limit, color in (
        (90, "#4c1"),
        (80, "#97ca00"),
        (70, "#a4a61d"),
        (60, "#dfb317"),
        (50, "#fe7d37"),
    ):
        if pct >= limit:
            return color
    return "#e05d44"


def main(xml_path: str, out_dir: str) -> int:
    root = ET.parse(xml_path).getroot()
    pct = float(root.get("line-rate", 0)) * 100
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    color = color_for(pct)
    (out / "coverage.svg").write_text(SVG.format(pct=round(pct), color=color), "utf-8")
    (out / "coverage.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "label": "coverage",
                "message": f"{pct:.0f}%",
                "color": color.lstrip("#"),
            }
        ),
        "utf-8",
    )
    rows = []
    for cls in root.iter("class"):
        lines = cls.find("lines")
        total = len(lines) if lines is not None else 0
        if total >= 150:
            rows.append(
                (float(cls.get("line-rate", 0)) * 100, total, cls.get("filename", "?"))
            )
    rows.sort()
    print(f"## Coverage: {pct:.1f}%\n")
    if rows:
        print(
            "Least-covered large modules:\n\n| Module | Lines | Covered |\n|---|---:|---:|"
        )
        for rate, total, name in rows[:10]:
            print(f"| `{name}` | {total} | {rate:.0f}% |")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
