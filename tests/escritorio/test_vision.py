def test_distances_are_answered_from_the_scene():
    from sergio_escritorio.vision import distance_answer, scene_sentence

    pairs = [
        {"a": "taza", "b": "celular", "m": 0.45},
        {"a": "taza", "b": "libro", "m": 0.3},
    ]
    assert distance_answer("¿a qué distancia está la taza del celular?", [], pairs) == (
        "Entre taza y celular hay unos 45 centímetros (calculado por el tamaño real de los objetos)."
    )
    assert "no estoy seguro" in scene_sentence(
        [{"kind": "objeto", "label": "silla", "doubt": "x"}]
    )
