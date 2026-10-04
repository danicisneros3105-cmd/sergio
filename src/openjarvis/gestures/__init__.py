"""Modo Stark: control espacial con las manos (estilo Tony Stark).

Crea figuras en el aire, agárralas, muévelas, escálalas y gíralas con dos
manos. Opcionalmente controla el ratón y las ventanas del escritorio.

Uso:
    python -m openjarvis.gestures.stark            # lienzo de figuras
    python -m openjarvis.gestures.stark --pantalla # también mueve el ratón
    sergio gestos --pantalla

Dependencias: ``uv sync --extra gestures`` (mediapipe + opencv).  Para
controlar el ratón/ventanas añade ``--extra screen-control`` (pyautogui).
"""

from openjarvis.gestures.stark import StarkApp, main

__all__ = ["StarkApp", "main"]
