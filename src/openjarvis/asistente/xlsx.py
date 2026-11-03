"""Real Excel workbooks (.xlsx) with no extra library, and reading them back.

The owner (3 Nov 2026): «Sergio, revisa mi informe de gastos y crea un Excel».
An .xlsx is a zip of XML files (Office Open XML, ECMA-376). This writes what
an expense report or a table needs: several sheets, a bold header that stays
on top while scrolling, filters, column widths, money / percent / date formats
and real formulas (totals with SUM, so the numbers stay live when edited).
Reading covers what people send: the first sheets' values (shared strings,
numbers, booleans, and dates as numbers) and CSV.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from xml.sax.saxutils import escape

FORMATS = {  # style index in styles.xml
    "texto": 0,
    "encabezado": 1,
    "numero": 2,
    "moneda": 3,
    "porcentaje": 4,
    "fecha": 5,
    "total": 6,
    "total_moneda": 7,
}
_EPOCH = dt.date(1899, 12, 30)
_OD = "application/vnd.openxmlformats-officedocument.spreadsheetml"
_REL = "/officeDocument/2006/relationships"


class XlsxError(ValueError):
    pass


def col_name(i: int) -> str:
    """0 → A, 25 → Z, 26 → AA."""
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def _sheet_name(name: str, used: set) -> str:
    clean = re.sub(r"[\[\]\*\?/\\:]", " ", name or "Hoja").strip()[:31] or "Hoja"
    base, n = clean, 2
    while clean.lower() in used:
        clean = f"{base[:28]} {n}"
        n += 1
    used.add(clean.lower())
    return clean


def _date_serial(value: Any) -> Optional[float]:
    if isinstance(value, dt.datetime):
        return (value - dt.datetime(1899, 12, 30)).total_seconds() / 86400
    if isinstance(value, dt.date):
        return float((value - _EPOCH).days)
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return float((dt.date.fromisoformat(value.strip()) - _EPOCH).days)
        except ValueError:
            return None
    return None


def _cell(ref: str, value: Any, style: int) -> str:
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    if isinstance(value, str) and value.startswith("="):
        return f'<c r="{ref}"{s}><f>{escape(value[1:])}</f></c>'
    if isinstance(value, bool):
        return f'<c r="{ref}"{s} t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{value!r}</v></c>'
    if style == FORMATS["fecha"]:
        serial = _date_serial(value)
        if serial is not None:
            return f'<c r="{ref}"{s}><v>{serial}</v></c>'
    text = escape(str(value)).replace("\n", "&#10;")
    return (
        f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
    )


def _number(value: Any) -> Any:
    """«$1.250,50», «1,250.50», «12 %» → numbers; anything else stays."""
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw or raw.startswith("=") or not re.search(r"\d", raw):
        return value
    pct = raw.endswith("%")
    s = re.sub(r"[^\d,.\-]", "", raw)
    if not re.fullmatch(r"-?[\d.,]+", s):
        return value
    if "," in s and "." in s:
        s = (
            s.replace(".", "").replace(",", ".")
            if s.rfind(",") > s.rfind(".")
            else s.replace(",", "")
        )
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = s.replace(",", ".") if len(tail) != 3 else s.replace(",", "")
    try:
        n = float(s)
    except ValueError:
        return value
    if pct:
        n /= 100
    return int(n) if n.is_integer() and not pct and "." not in s else n


def _sheet_xml(sheet: Dict[str, Any]) -> str:
    cols: List[str] = [str(c) for c in sheet.get("columnas") or []]
    rows: List[Sequence[Any]] = sheet.get("filas") or []
    fmt: Dict[str, str] = sheet.get("formatos") or {}
    totals: List[str] = [str(t) for t in sheet.get("totales") or []]
    kinds = [fmt.get(c, "") for c in cols]
    width = max([len(cols)] + [len(r) for r in rows] + [1])
    out_rows: List[str] = []
    widths = [max(8, min(60, len(c) + 2)) for c in cols] + [10] * (width - len(cols))
    r = 1
    if cols:
        cells = "".join(
            _cell(f"{col_name(i)}1", c, FORMATS["encabezado"])
            for i, c in enumerate(cols)
        )
        out_rows.append(f'<row r="1">{cells}</row>')
        r = 2
    first_data = r
    for row in rows:
        cells = []
        for i, value in enumerate(row):
            kind = kinds[i] if i < len(kinds) else ""
            if kind in ("numero", "moneda", "porcentaje"):
                value = _number(value)
            style = FORMATS.get(kind, 0)
            cells.append(_cell(f"{col_name(i)}{r}", value, style))
            widths[i] = max(widths[i], min(60, len(str(value)) + 2))
        out_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
        r += 1
    last_data = r - 1
    if totals and rows:
        cells = [_cell(f"A{r}", "Total", FORMATS["total"])]
        for i, c in enumerate(cols):
            if c in totals and i > 0:
                style = (
                    FORMATS["total_moneda"]
                    if kinds[i] == "moneda"
                    else FORMATS["total"]
                )
                ref = col_name(i)
                cells.append(
                    _cell(
                        f"{ref}{r}", f"=SUM({ref}{first_data}:{ref}{last_data})", style
                    )
                )
        out_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    col_xml = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
        for i, w in enumerate(widths)
    )
    pane = (
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        if cols
        else ""
    )
    auto = (
        f'<autoFilter ref="A1:{col_name(width - 1)}{max(1, last_data)}"/>'
        if cols and rows
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{pane}<cols>{col_xml}</cols><sheetData>{''.join(out_rows)}</sheetData>{auto}</worksheet>"
    )


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;$&quot;#,##0.00"/>'
    '<numFmt numFmtId="165" formatCode="yyyy-mm-dd"/></numFmts>'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF2EFEA"/></patternFill></fill></fills>'
    '<borders count="2"><border/><border><top style="thin"/></border></borders>'
    '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
    '<cellXfs count="8">'
    "<xf/>"
    '<xf fontId="1" fillId="2" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="4" applyNumberFormat="1"/>'
    '<xf numFmtId="164" applyNumberFormat="1"/>'
    '<xf numFmtId="10" applyNumberFormat="1"/>'
    '<xf numFmtId="165" applyNumberFormat="1"/>'
    '<xf fontId="1" borderId="1" applyFont="1" applyBorder="1"/>'
    '<xf numFmtId="164" fontId="1" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>'
    "</cellXfs></styleSheet>"
)


def write(path: Path | str, sheets: List[Dict[str, Any]]) -> Path:
    """Writes a workbook. Each sheet: ``nombre``, ``columnas``, ``filas``,
    ``formatos`` ({columna: texto|numero|moneda|porcentaje|fecha}) and
    ``totales`` (columns that get a SUM row)."""
    if not sheets:
        raise XlsxError("No hay nada que poner en el Excel.")
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        path = path.with_suffix(".xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    used: set = set()
    names = [
        _sheet_name(str(s.get("nombre") or f"Hoja {i + 1}"), used)
        for i, s in enumerate(sheets)
    ]
    ns = "http://schemas.openxmlformats.org"
    tmp = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Types xmlns="{ns}/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{_OD}.sheet.main+xml"/>'
            f'<Override PartName="/xl/styles.xml" ContentType="{_OD}.styles+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(len(sheets))
            )
            + "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{ns}/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{ns}{_REL}/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<workbook xmlns="{ns}/spreadsheetml/2006/main" xmlns:r="{ns}/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                for i, n in enumerate(names)
            )
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{ns}/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i + 1}" Type="{ns}/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{i + 1}.xml"/>'
                for i in range(len(sheets))
            )
            + f'<Relationship Id="rId{len(sheets) + 1}" Type="{ns}{_REL}/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        z.writestr("xl/styles.xml", _STYLES)
        for i, sheet in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet_xml(sheet))
    tmp.replace(path)
    return path


# -- reading ------------------------------------------------------------------------


def _ref_col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):  # type: ignore[union-attr]
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read(path: Path | str, max_rows: int = 2000) -> List[Dict[str, Any]]:
    """The sheets of an .xlsx (or a .csv) as ``{nombre, filas}``."""
    from openjarvis.security import (
        safe_xml as ET,
    )  # no DOCTYPE or entities from outside

    path = Path(path)
    if path.suffix.lower() in (".csv", ".tsv"):
        text = path.read_text("utf-8-sig", errors="replace")
        dialect = (
            csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            if text.strip()
            else csv.excel
        )
        rows = [r for r in csv.reader(io.StringIO(text), dialect)][:max_rows]
        return [{"nombre": path.stem, "filas": rows}]
    if path.suffix.lower() != ".xlsx":
        raise XlsxError(
            "Solo leo .xlsx y .csv (un .xls viejo: ábralo y guárdelo como .xlsx)."
        )
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(path) as z:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{m}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{m}t")))
        rels = {
            r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        }
        out = []
        for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{m}sheet"):
            target = rels.get(sh.get(f"{r_ns}id"), "")
            target = target.lstrip("/")
            target = target if target.startswith("xl/") else f"xl/{target}"
            if target not in z.namelist():
                continue
            rows: List[List[Any]] = []
            for row in ET.fromstring(z.read(target)).iter(f"{m}row"):
                values: List[Any] = []
                for c in row.iter(f"{m}c"):
                    i = _ref_col(c.get("r", "A1"))
                    while len(values) < i:
                        values.append("")
                    kind = c.get("t")
                    v = c.find(f"{m}v")
                    f = c.find(f"{m}f")
                    if f is not None and (v is None or v.text is None):
                        values.append(
                            "=" + (f.text or "")
                        )  # a formula not computed yet
                        continue
                    if kind == "s" and v is not None:
                        values.append(shared[int(v.text or 0)])
                    elif kind == "inlineStr":
                        values.append("".join(t.text or "" for t in c.iter(f"{m}t")))
                    elif kind == "b" and v is not None:
                        values.append(v.text == "1")
                    elif v is not None and v.text is not None:
                        try:
                            n = float(v.text)
                            values.append(int(n) if n.is_integer() else n)
                        except ValueError:
                            values.append(v.text)
                    else:
                        values.append("")
                rows.append(values)
                if len(rows) >= max_rows:
                    break
            out.append({"nombre": sh.get("name"), "filas": rows})
        return out


__all__ = ["XlsxError", "col_name", "read", "write"]
