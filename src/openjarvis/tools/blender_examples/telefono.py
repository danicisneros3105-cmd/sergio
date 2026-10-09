"""Seed: a phone built with Sergio's kit (extrude, boolean cut, copies, mirror, array)."""

import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
SERGIO_LAYOUT = [
    {"part": "Cuerpo", "center_cm": [0, 0, 7.5], "size_cm": [7.2, 0.8, 15.0]},
    {"part": "Pantalla", "center_cm": [0, -0.41, 7.5], "size_cm": [6.8, 0.02, 14.6]},
]
alu = kit_material("Aluminio", (0.55, 0.56, 0.6), metallic=1.0, roughness=0.3)
vidrio = kit_material("Vidrio negro", (0.01, 0.01, 0.015), roughness=0.05, coat=1.0)
lente = kit_material("Lente", (0.02, 0.02, 0.03), roughness=0.02, transmission=0.3)


def cuerpo():
    body = kit_extrude(
        "Cuerpo",
        kit_rounded_rect(0.072, 0.150, 0.009),
        0.008,
        loc=(0, 0, 0.075),
        rot=(90, 0, 0),
        bevel=0.0015,
        mat=alu,
    )
    puerto = kit_box("Puerto_corte", (0.009, 0.004, 0.004), loc=(0, 0, 0.0005))
    kit_cut(body, puerto)
    return [body, puerto]


def pantalla():
    return kit_extrude(
        "Pantalla",
        kit_rounded_rect(0.068, 0.146, 0.008),
        0.0004,
        loc=(0, -0.0041, 0.075),
        rot=(90, 0, 0),
        mat=vidrio,
    )


def camaras():
    bump = kit_extrude(
        "Modulo",
        kit_rounded_rect(0.032, 0.032, 0.007),
        0.0015,
        loc=(-0.015, 0.0047, 0.128),
        rot=(90, 0, 0),
        bevel=0.0005,
        mat=vidrio,
    )
    l1 = kit_cylinder(
        "Lente_1", 0.006, 0.0015, loc=(-0.022, 0.0058, 0.135), rot=(90, 0, 0), mat=lente
    )
    l2 = kit_copy(l1, loc=(-0.008, 0.0058, 0.135), name="Lente_2")
    l3 = kit_copy(l1, loc=(-0.022, 0.0058, 0.121), name="Lente_3")
    flash = kit_sphere(
        "Flash",
        0.0022,
        loc=(-0.008, 0.0056, 0.121),
        scale=(1, 0.4, 1),
        mat=kit_material("Flash", (1, 0.95, 0.8), emission=(1, 0.9, 0.7), strength=0.5),
    )
    return [bump, l1, l2, l3, flash]


def botones():
    b = kit_box(
        "Boton_vol",
        (0.0012, 0.003, 0.012),
        loc=(0.0366, 0, 0.11),
        bevel=0.0005,
        mat=alu,
    )
    return [b, kit_mirror_x(b, "Boton_power")]


def tornillos():
    t = kit_cylinder(
        "Tornillo", 0.0007, 0.0005, loc=(0.004, 0.0, 0.0002), mat=alu, verts=12
    )
    return kit_array_circle(t, 4, 0.004, z=0.0002)


objs = cuerpo() + [pantalla()] + camaras() + botones() + tornillos()
kit_parent("Teléfono", objs)
