"""Organizer: alarms, sticky notes, voice orders, the window."""

from __future__ import annotations

from datetime import datetime

import pytest
from sergio_escritorio import organizer
from sergio_escritorio.organizer import (
    Alarms,
    Notes,
    parse_alarm,
    parse_days,
    parse_note,
)

MONDAY_15 = datetime(2026, 10, 5, 15, 0)  # a Monday


def test_days_in_words():
    assert parse_days("de lunes a viernes") == [0, 1, 2, 3, 4]
    assert parse_days("todos los días") == list(range(7))
    assert parse_days("los martes y jueves") == [1, 3]
    assert parse_days("fines de semana") == [5, 6]
    assert parse_days("de viernes a lunes") == [4, 5, 6, 0]
    assert parse_days("mañana") == []


def test_alarm_orders():
    assert parse_alarm(
        "pon una alarma a las 6:30 de lunes a viernes para ir al gym", MONDAY_15
    ) == (6, 30, [0, 1, 2, 3, 4], "ir al gym")
    assert parse_alarm("despiértame a las 7", MONDAY_15)[:2] == (7, 0)  # not 19:00
    assert parse_alarm("alarma a las 8 de la noche", MONDAY_15)[:2] == (20, 0)
    assert parse_alarm("recuérdame en 5 minutos", MONDAY_15) is None


def test_alarms_ring_on_their_days_and_once_ones_switch_off(tmp_path):
    clock = [MONDAY_15.replace(hour=6, minute=29).timestamp()]
    rang = []
    alarms = Alarms(tmp_path / "a.json", rang.append, clock=lambda: clock[0])
    weekday = alarms.add(6, 30, [0, 1, 2, 3, 4], "gym")
    once = alarms.add(6, 30, [], "una vez")
    assert alarms.check() == []
    clock[0] += 70  # 6:30:10
    assert {a.id for a in alarms.check()} == {weekday.id, once.id}
    assert alarms.check() == []  # not twice in the same minute
    assert not alarms.items[[a.id for a in alarms.items].index(once.id)].enabled
    saturday = datetime(2026, 10, 10, 6, 30, 5).timestamp()
    clock[0] = saturday
    assert alarms.check() == []  # weekdays only
    again = Alarms(tmp_path / "a.json", rang.append)
    assert {a.label for a in again.items} == {"gym", "una vez"}


def test_snooze_rings_again_after_five_minutes(tmp_path):
    clock = [MONDAY_15.timestamp()]
    rang = []
    alarms = Alarms(tmp_path / "a.json", rang.append, clock=lambda: clock[0])
    alarm = alarms.add(15, 0)
    alarms.snooze(alarm.id)
    clock[0] += 290
    assert alarms.check() == []
    clock[0] += 20
    assert alarms.check() == [alarm]


def test_next_time_and_description():
    alarm = organizer.Alarm("x", 7, 0, [5, 6], "correr")
    assert alarm.next_time(MONDAY_15) == datetime(2026, 10, 10, 7, 0)
    assert alarm.describe() == "07:00 (fines de semana) · correr"


def test_notes_and_their_orders(tmp_path):
    assert parse_note("nota: comprar leche") == ("comprar leche", "amarillo")
    assert parse_note("crea una nota rosa que diga llamar a mamá") == (
        "llamar a mamá",
        "rosa",
    )
    assert parse_note("toma notas de la reunión") is None
    notes = Notes(tmp_path / "n.json")
    note = notes.add("comprar leche", "verde")
    notes.update(note.id, x=100, y=200)
    again = Notes(tmp_path / "n.json")
    assert again.items[0].x == 100 and again.find("LECHE")
    assert again.remove(note.id) and not Notes(tmp_path / "n.json").items


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("pon una alarma a las 6:30 de lunes a viernes", "alarm"),
        ("despiértame en 20 minutos", "reminder"),
        ("cancela la alarma de las 7", "alarm_remove"),
        ("cuáles son mis alarmas", "alarms_list"),
        ("nota: comprar leche", "note"),
        ("muéstrame mis notas", "notes_show"),
        ("abre el organizador", "organizer"),
        ("toma notas de la reunión", "meeting_start"),
    ],
)
def test_organizer_orders(said, kind):
    from sergio_escritorio.quick import parse_quick

    assert parse_quick(said).kind == kind


def test_widgets_draw(tmp_path):
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.jarvis import Reminders
    from sergio_escritorio.organizer_ui import AlarmCard, NotesBoard, OrganizerWindow

    _app = QApplication.instance() or QApplication([])
    notes = Notes(tmp_path / "n.json")
    board = NotesBoard(notes)
    sticky = board.show(notes.add("comprar leche"))
    assert sticky.grab().width() > 100
    alarms = Alarms(tmp_path / "a.json", lambda a: None)
    alarm = alarms.add(7, 0, [0], "gym")
    window = OrganizerWindow(
        alarms,
        notes,
        board,
        Reminders(None, lambda r: None),
        lambda: [
            {
                "tipo": "tarea",
                "materia": "Física",
                "titulo": "Informe",
                "fecha": "2026-10-09",
            }
        ],
    )
    window.open(1)
    assert (
        window.alarm_list.count() == 1
        and window.note_list.count() == 1
        and "Física" in window.homework_list.item(0).text()
    )
    window.note_text.setText("otra")
    window._add_note()
    assert len(notes.items) == 2 and len(board.widgets) == 2
    card = AlarmCard(alarm, lambda: None, lambda: None)
    assert card.grab().width() > 300
    for w in (window, card, *board.widgets.values()):
        w.close()


def test_notepad_is_still_an_app():
    from sergio_escritorio.quick import parse_quick

    assert parse_quick("abre el bloc de notas").kind != "notes_show"
