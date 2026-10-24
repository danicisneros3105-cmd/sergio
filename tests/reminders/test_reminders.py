"""Goals, medications and reminders: the store, the routes and Sergio's tool."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from openjarvis.reminders.store import ReminderStore, goals_block


@pytest.fixture
def store(tmp_path):
    return ReminderStore(tmp_path / "r.db")


def test_a_medication_is_due_at_its_time_until_it_is_taken(store):
    med = store.add(
        "medicina", "Losartán", times=["08:00", "20:00"], extra={"dose": "50 mg"}
    )
    morning = datetime(2026, 10, 24, 8, 30)
    due = store.due(morning)
    assert [(d["title"], d["at"]) for d in due] == [("Losartán", "08:00")]
    assert store.mark(med["id"], due[0]["slot"], "hecho")
    assert store.due(morning) == []
    assert store.due(datetime(2026, 10, 24, 12, 0)) == []  # past the window
    assert [d["at"] for d in store.due(datetime(2026, 10, 24, 20, 5))] == ["20:00"]


def test_adherence_counts_only_real_answers(store, monkeypatch):
    import openjarvis.reminders.store as mod

    created = datetime(2026, 10, 20, 7, 0)
    monkeypatch.setattr(mod.time, "time", lambda: created.timestamp())
    med = store.add("medicina", "Vitamina D", times=["09:00"])
    now = datetime(2026, 10, 24, 10, 0)
    for day in (20, 21, 23):
        store.mark(med["id"], f"2026-10-{day}T09:00", "hecho")
    store.mark(med["id"], "2026-10-22T09:00", "saltado")
    adh = store.adherence(med["id"], now=now)
    assert adh == {"due": 5, "taken": 3, "share": 0.6}


def test_days_and_one_off_dates(store):
    store.add("recordatorio", "Basura", times=["19:00"], days=[1, 3])  # Tue, Thu
    store.add("recordatorio", "Dentista", times=["15:00"], date="2026-10-30")
    week = store.occurrences(datetime(2026, 10, 26), datetime(2026, 11, 1, 23, 59))
    assert [(o["item"]["title"], o["when"].strftime("%a %H:%M")) for o in week] == [
        ("Basura", "Tue 19:00"),
        ("Basura", "Thu 19:00"),
        ("Dentista", "Fri 15:00"),
    ]


def test_bad_input_is_cleaned_or_refused(store):
    item = store.add(
        "recordatorio", "  agua  ", times=["7:5", "25:00", "07:30"], days=[9, 2]
    )
    assert (
        item["title"] == "agua" and item["times"] == ["07:30"] and item["days"] == [2]
    )
    with pytest.raises(ValueError):
        store.add("otro", "x")
    with pytest.raises(ValueError):
        store.add("meta", "   ")


def test_sergio_keeps_the_goals_in_mind(store):
    assert goals_block(store) == ""
    store.add("meta", "Correr 5 km en diciembre", extra={"why": "salud"})
    store.add("medicina", "Metformina", times=["08:00"], extra={"dose": "850 mg"})
    paused = store.add("meta", "Aprender alemán")
    store.update(paused["id"], active=False)
    block = goals_block(store)
    assert "Correr 5 km" in block and "Metformina, 850 mg a las 08:00" in block
    assert "alemán" not in block and "consejo médico" in block


def test_the_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import reminder_routes

    st = ReminderStore(tmp_path / "r.db")
    monkeypatch.setattr(reminder_routes, "_store", lambda: st)
    app = FastAPI()
    app.include_router(reminder_routes.router)
    c = TestClient(app)
    med = c.post(
        "/v1/reminders",
        json={
            "kind": "medicina",
            "title": "Ibuprofeno",
            "times": ["10:00"],
            "extra": {"dose": "400 mg"},
        },
    ).json()
    assert med["adherence"]["due"] >= 0
    assert (
        c.post("/v1/reminders", json={"kind": "nada", "title": "x"}).status_code == 422
    )
    items = c.get("/v1/reminders").json()["items"]
    assert [i["title"] for i in items] == ["Ibuprofeno"]
    assert (
        c.put(f"/v1/reminders/{med['id']}", json={"active": False}).json()["active"]
        is False
    )
    assert c.post(
        f"/v1/reminders/{med['id']}/done", json={"slot": "2026-10-24T10:00"}
    ).json()["ok"]
    assert c.delete(f"/v1/reminders/{med['id']}").json()["ok"]
    assert c.delete(f"/v1/reminders/{med['id']}").status_code == 404


def test_the_tool(tmp_path, monkeypatch):
    import openjarvis.reminders as pkg
    from openjarvis.tools.reminders_tool import RemindersTool

    st = ReminderStore(tmp_path / "r.db")
    monkeypatch.setattr(pkg, "get_store", lambda: st)
    tool = RemindersTool()
    out = tool.execute(
        action="add", kind="medicina", title="Omeprazol", times=["07:00"], dose="20 mg"
    )
    assert out.success and "Omeprazol (20 mg)" in out.content
    iid = st.items()[0]["id"]
    assert "Omeprazol" in tool.execute(action="list").content
    assert tool.execute(action="done", id=iid, slot="2026-10-24T07:00").success
    assert tool.execute(action="remove", id=iid).success
    assert not tool.execute(action="add", kind="medicina", title="").success
    from openjarvis.connectome.neurons import NEURONS

    assert "reminders" in NEURONS["agenda"].tools


def test_upcoming_lists_the_next_day(store):
    store.add("recordatorio", "Llamar a mamá", times=["18:00"])
    now = datetime(2026, 10, 24, 17, 0)
    up = store.upcoming(now, hours=24)
    assert up[0]["at"] == "18:00" and up[0]["slot"] == "2026-10-24T18:00"
    assert all(
        datetime.strptime(u["slot"], "%Y-%m-%dT%H:%M") <= now + timedelta(hours=24)
        for u in up
    )
