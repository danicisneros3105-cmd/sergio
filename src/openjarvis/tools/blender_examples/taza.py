"""Seed: a white ceramic cup with saucer, built with Sergio's kit (lathe + tube + text)."""

import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
SERGIO_LAYOUT = [
    {"part": "Taza", "center_cm": [0, 0, 5.6], "size_cm": [9, 9, 10]},
    {"part": "Asa", "center_cm": [5.9, 0, 5.6], "size_cm": [3.2, 1.2, 6]},
    {"part": "Plato", "center_cm": [0, 0, 0.5], "size_cm": [15, 15, 1]},
]
ceramica = kit_material("Cerámica", (0.93, 0.92, 0.88), roughness=0.25, coat=0.5)
cafe = kit_material("Café", (0.12, 0.06, 0.03), roughness=0.1)


def plato():
    return kit_lathe(
        "Plato",
        [
            (0, 0),
            (0.05, 0),
            (0.07, 0.006),
            (0.075, 0.01),
            (0.072, 0.011),
            (0.05, 0.005),
            (0, 0.005),
        ],
        mat=ceramica,
    )


def taza():
    return kit_lathe(
        "Taza",
        [
            (0, 0.006),
            (0.032, 0.006),
            (0.036, 0.009),
            (0.045, 0.106),
            (0.042, 0.106),
            (0.034, 0.014),
            (0, 0.014),
        ],
        mat=ceramica,
    )


def liquido():
    return kit_cylinder("Café", 0.0405, 0.002, loc=(0, 0, 0.09), mat=cafe, verts=64)


def asa():
    return kit_tube(
        "Asa",
        [
            (0.043, 0, 0.088),
            (0.068, 0, 0.082),
            (0.074, 0, 0.056),
            (0.064, 0, 0.032),
            (0.041, 0, 0.027),
        ],
        0.006,
        mat=ceramica,
    )


def letrero():
    return kit_text(
        "Logo",
        "SERGIO",
        size=0.012,
        depth=0.001,
        loc=(0, -0.0425, 0.06),
        rot=(90, 0, 0),
        mat=cafe,
    )


parts = [plato(), taza(), liquido(), asa(), letrero()]
kit_parent("Taza de café", parts)
