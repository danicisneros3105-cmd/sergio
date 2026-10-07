"""Blender Pro's build score: spatial mistakes make a build worse."""

from sergio_escritorio.media import blender_score, worse_build

BASE = "SERGIO_SAVED x.blend 10\nSERGIO_PARTS 10 meshes: a\n"


def test_floating_and_misplaced_parts_lower_the_score():
    clean = blender_score(BASE)
    messy = blender_score(BASE + "SERGIO_FLOATING Lente touches nothing\nSERGIO_LAYOUT_OFF Pata: ...\n")
    assert messy == clean - 1.0
    assert blender_score("nothing saved") == -1.0 and worse_build(-1.0, clean)
