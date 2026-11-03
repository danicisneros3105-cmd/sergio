"""Excel files Sergio writes open in Excel, with formats and live totals."""

from __future__ import annotations

import zipfile

import pytest

from openjarvis.asistente import xlsx


def test_write_and_read_back(tmp_path):
    path = xlsx.write(
        tmp_path / "gastos",
        [
            {
                "nombre": "Gastos: octubre/2026",
                "columnas": ["Fecha", "Concepto", "Monto"],
                "filas": [
                    ["2026-10-01", "Almuerzo & café", "$12,50"],
                    ["2026-10-02", "Uber", "8.75"],
                ],
                "formatos": {"Fecha": "fecha", "Monto": "moneda"},
                "totales": ["Monto"],
            },
            {"nombre": "Gastos: octubre/2026", "columnas": ["A"], "filas": [[1]]},
        ],
    )
    assert path.suffix == ".xlsx"
    with zipfile.ZipFile(path) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
        book = z.read("xl/workbook.xml").decode()
    assert (
        "<f>SUM(C2:C3)</f>" in sheet
        and 'state="frozen"' in sheet
        and "autoFilter" in sheet
    )
    assert "/" not in book.split("<sheets>")[1].split('name="')[1].split('"')[0]
    sheets = xlsx.read(path)
    rows = sheets[0]["filas"]
    assert rows[0] == ["Fecha", "Concepto", "Monto"]
    assert rows[1][1] == "Almuerzo & café" and rows[1][2] == 12.5 and rows[2][2] == 8.75
    assert rows[3][0] == "Total" and rows[3][2] == "=SUM(C2:C3)"
    assert len({s["nombre"] for s in sheets}) == 2


@pytest.mark.parametrize(
    "raw,num",
    [
        ("$1.250,50", 1250.5),
        ("1,250.50", 1250.5),
        ("12 %", 0.12),
        ("1,5", 1.5),
        ("abc", "abc"),
    ],
)
def test_amounts_written_by_people_become_numbers(raw, num):
    assert xlsx._number(raw) == num


def test_reads_csv_and_refuses_old_xls(tmp_path):
    (tmp_path / "a.csv").write_text("concepto;monto\ntaxi;5\n", "utf-8")
    assert xlsx.read(tmp_path / "a.csv")[0]["filas"][1] == ["taxi", "5"]
    (tmp_path / "b.xls").write_bytes(b"x")
    with pytest.raises(xlsx.XlsxError):
        xlsx.read(tmp_path / "b.xls")
    assert xlsx.col_name(0) == "A" and xlsx.col_name(26) == "AA"
