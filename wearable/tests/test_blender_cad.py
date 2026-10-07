"""Prueba del CAD con Blender como módulo de Python (pip install bpy).

Se salta sola si ``bpy`` no está instalado (Blender 4.x lo publica en PyPI
para la versión de Python con la que se compila, p. ej. bpy 4.2 -> Python 3.11).
"""

from __future__ import annotations

from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy")
bmesh = pytest.importorskip("bmesh")

SCRIPT = Path(__file__).resolve().parents[1] / "blender" / "gafas_stark_cad.py"


def _ejecutar(tmp_path):
    codigo = SCRIPT.read_text(encoding="utf-8")
    codigo = codigo.replace("EXPORTAR_STL = True", "EXPORTAR_STL = False")
    exec(compile(codigo, str(SCRIPT), "exec"), {"__name__": "__main__"})


def _medidas(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    xs, ys, zs = zip(*[(v.co.x, v.co.y, v.co.z) for v in bm.verts], strict=True)
    abiertas = sum(1 for e in bm.edges if not e.is_manifold)
    volumen = bm.calc_volume()
    bm.free()
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)), abiertas, volumen


def _solido(obj, punto):
    """¿El punto está dentro del material? (rayo hacia +X, paridad de cortes)."""
    from mathutils import Vector

    origen, cortes = Vector(punto), 0
    while True:
        ok, pos, _n, _i = obj.ray_cast(origen, Vector((1, 0, 0)))
        if not ok:
            return cortes % 2 == 1
        cortes += 1
        origen = pos + Vector((1e-4, 0, 0))


def test_geometria_de_las_gafas(tmp_path):
    _ejecutar(tmp_path)
    escena = bpy.context.scene
    assert escena.unit_settings.length_unit == "MILLIMETERS"
    coleccion = bpy.data.collections["Hardware_Stark"]
    nombres = sorted(o.name for o in coleccion.objects)
    assert nombres == ["Frontal_Gafas", "Varilla_Derecha", "Varilla_Izquierda"]

    frontal = bpy.data.objects["Frontal_Gafas"]
    dims, abiertas, _ = _medidas(frontal)
    assert dims == pytest.approx((144.0, 10.0, 48.0), abs=1e-3)
    assert abiertas == 0
    # Hueco del lente derecho (centro en x=36): vacío. Puente (x=0): sólido.
    assert not _solido(frontal, (36.0, 0.0, -1.25))
    assert _solido(frontal, (0.0, 0.0, 0.0))
    # Túnel superior (z=21.125): vacío a lo largo de todo el aro superior...
    for x in (-60.0, -30.0, 0.0, 30.0, 60.0):
        assert not _solido(frontal, (x, 0.0, 21.125))
    # ...con material a 1.4 mm por encima y por debajo (pared de 1.62 mm).
    assert _solido(frontal, (0.0, 0.0, 21.125 + 1.4))
    assert _solido(frontal, (0.0, 0.0, 21.125 - 1.4))
    # No asoma por los laterales: el extremo exterior sigue siendo sólido.
    assert _solido(frontal, (70.0, 0.0, 21.125))
    # El codo sale por la cara trasera, sobre el eje de la varilla (x=±67).
    assert not _solido(frontal, (67.0, -4.0, 21.125))
    # Cámara en la bisagra derecha: alojamiento abierto al frente, fondo a
    # 5 mm, y su canal sube por dentro del aro hasta el túnel.
    assert not _solido(frontal, (65.75, 4.0, 4.0))
    assert _solido(frontal, (65.75, -2.0, 4.0))
    assert not _solido(frontal, (65.75, 1.0, 14.0))
    assert _solido(frontal, (-65.75, 4.0, 4.0))  # el lado izquierdo no tiene cámara
    # Esquinas redondeadas: la arista viva de la caja ya no existe.
    assert not _solido(frontal, (71.5, 0.0, 23.5))

    for nombre, signo in (("Varilla_Derecha", 1), ("Varilla_Izquierda", -1)):
        varilla = bpy.data.objects[nombre]
        dims, abiertas, volumen = _medidas(varilla)
        assert dims == pytest.approx((10.0, 151.0, 12.0), abs=1e-3)
        assert abiertas == 0
        x = signo * 67.0
        # Túnel continuo desde el frontal hasta la punta.
        for y in (-6.0, -50.0, -100.0, -150.0):
            assert not _solido(varilla, (x, y, 21.125))
        # Cavidad del imán: Ø3.1 -> vacío a 1.45 mm del eje en la punta, pero
        # sólido a esa misma distancia en el túnel (Ø2.5).
        assert not _solido(varilla, (x, -154.0, 21.125 - 1.45))
        assert _solido(varilla, (x, -140.0, 21.125 - 1.45))
        # Volumen = caja - túnel - cavidad (± facetado).
        assert volumen == pytest.approx(16_505, abs=5)
