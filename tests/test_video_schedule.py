"""Videos on a schedule (video_essay/schedule.py): made on time, never posted alone."""

from __future__ import annotations

import pytest

from openjarvis.video_essay import schedule


class Made:
    def __init__(self, n: int) -> None:
        self.id = f"job{n}"


def test_a_schedule_starts_on_time_with_a_new_angle_each_time(tmp_path):
    item = schedule.add(
        "datos curiosos del espacio",
        every_hours=3,
        mode="post",
        home=tmp_path,
        now=1000,
    )
    assert item["modo"] == "post" and item["formato"] == "9:16"
    orders = []

    def start(order):
        orders.append(order)
        return Made(len(orders))

    free = lambda order: (None, "")  # noqa: E731
    assert (
        schedule.tick(home=tmp_path, now=1000, start=start, guard=free) == []
    )  # not yet (in a minute)
    assert schedule.tick(home=tmp_path, now=1061, start=start, guard=free) == [
        item["id"]
    ]
    assert "número 1" in orders[0]["prompt"] and orders[0]["mode"] == "post"
    assert (
        schedule.tick(home=tmp_path, now=1061 + 3600, start=start, guard=free) == []
    )  # every 3 h
    # the next one drifts a little (humano.stagger: up to 45 min), so it is
    # due by 3 h 46 min, not to the second at 3 h
    schedule.tick(home=tmp_path, now=1061 + 3 * 3600 + 46 * 60, start=start, guard=free)
    assert "número 2" in orders[1]["prompt"]
    assert schedule.load(tmp_path)[0]["hechos"] == ["job1", "job2"]


def test_busy_or_daily_cap_waits_instead_of_piling_up(tmp_path):
    schedule.add("recetas en 30 segundos", every_hours=1, home=tmp_path, now=0)
    started = []
    busy = lambda order: (object(), "tope diario")  # noqa: E731
    assert schedule.tick(home=tmp_path, now=100, start=started.append, guard=busy) == []
    item = schedule.load(tmp_path)[0]
    assert started == [] and "máximo" in item["nota"] and item["proximo"] == 100 + 900


def test_paused_or_removed_schedules_do_nothing(tmp_path):
    item = schedule.add("tips de fotografía", every_hours=24, home=tmp_path, now=0)
    schedule.set_active(item["id"], False, home=tmp_path)
    assert (
        schedule.tick(
            home=tmp_path,
            now=10**9,
            start=lambda o: Made(1),
            guard=lambda o: (None, ""),
        )
        == []
    )
    assert schedule.remove(item["id"], home=tmp_path) and schedule.load(tmp_path) == []
    with pytest.raises(ValueError):
        schedule.add("x", home=tmp_path)
    with pytest.raises(ValueError):
        schedule.add("algo válido", every_hours=2, home=tmp_path)


def test_routes_list_add_and_posting_needs_the_owner(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server.personal_routes import router
    from openjarvis.video_essay import job as jobs

    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    monkeypatch.setattr(jobs, "jobs_dir", lambda: tmp_path / "video_jobs")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    out = client.post(
        "/v1/personal/videos", json={"idea": "historia de los autos", "cada_horas": 3}
    ).json()
    assert out["programados"][0]["cada_horas"] == 3 and out["listos"] == []
    assert [m["id"] for m in out["modos"]] == ["test", "basic", "post", "cinema"]
    assert (
        client.post(
            "/v1/personal/videos", json={"idea": "a", "cada_horas": 3}
        ).status_code
        == 400
    )
    # A finished scheduled video waits for the owner's tap; then it is handed over.
    job = jobs.create({"prompt": "x", "mode": "test"}, tmp_path / "video_jobs")
    package = {"title": "Autos", "description": "d"}
    job.update(
        status="listo", result={"url": "/v1/creator/media/v.mp4", "package": package}
    )
    items = schedule.load()
    items[0]["hechos"] = [job.id]
    schedule._save(items)
    listos = client.get("/v1/personal/videos").json()["listos"]
    assert listos == [
        {
            "job": job.id,
            "titulo": "Autos",
            "descripcion": "d",
            "video": "/v1/creator/media/v.mp4",
        }
    ]
    posted = client.post(f"/v1/personal/videos/listos/{job.id}/publicar").json()
    assert posted["titulo"] == "Autos"
    assert client.get("/v1/personal/videos").json()["listos"] == []
    item_id = items[0]["id"]
    paused = client.put(f"/v1/personal/videos/{item_id}", json={"activo": False}).json()
    assert paused["programados"][0]["activo"] is False
    assert client.delete(f"/v1/personal/videos/{item_id}").json()["programados"] == []
