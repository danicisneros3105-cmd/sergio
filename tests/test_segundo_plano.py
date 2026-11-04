"""Work left running in the background (owner, 4 Nov 2026: «mejora la
ejecución en segundo plano»)."""

from __future__ import annotations

from openjarvis.asistente import tareas


def test_a_check_runs_later_and_tells_when_done(tmp_path):
    told = []
    task = tareas.start(
        "revisar", "colegio", home=tmp_path, thread=False,
        check=lambda site, steps: {"estado": "ok", "texto": "Tarea de mate: página 40"},
        tell=told.append,
    )  # fmt: skip
    assert task["estado"] == "en_cola"
    out = tareas.run_once(
        task["id"], home=tmp_path, tell=told.append,
        check=lambda site, steps: {"estado": "ok", "texto": "Tarea de mate: página 40"},
    )  # fmt: skip
    assert out["estado"] == "listo" and "página 40" in out["texto"]
    assert told and "Listo" in told[0]
    assert "página 40" in tareas.plain(out)["texto"]


def test_a_failure_is_retried_once_then_told(tmp_path):
    calls, slept, told = [], [], []

    def flaky(site, steps):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("lento")
        return {"estado": "ok", "texto": "ok"}

    t = tareas.start("revisar", "banco", home=tmp_path, thread=False)
    out = tareas.run_once(
        t["id"], home=tmp_path, check=flaky, tell=told.append, sleep=slept.append
    )
    assert (
        out["estado"] == "listo" and len(calls) == 2 and slept == [tareas.RETRY_WAIT_S]
    )

    def broken(site, steps):
        raise RuntimeError("caído")

    t2 = tareas.start("revisar", "banco", home=tmp_path, thread=False)
    out2 = tareas.run_once(
        t2["id"], home=tmp_path, check=broken, tell=told.append, sleep=lambda s: None
    )
    assert (
        out2["estado"] == "error" and "caído" in out2["error"] and "No pude" in told[-1]
    )


def test_a_watch_tells_only_when_the_page_really_changes(tmp_path):
    pages = iter([
        "Notas\nMate: 8\nActualizado 10:01",
        "Notas\nMate: 8\nActualizado 10:31",  # only the clock moved
        "Notas\nMate: 8\nFísica: 9\nActualizado 11:01",
    ])  # fmt: skip
    told = []
    t = tareas.start(
        "vigilar", "colegio", cada_min=1, veces=3, home=tmp_path, thread=False
    )
    assert t["cada_min"] == tareas.MIN_EVERY_MIN  # never more often than every 5 min
    check = lambda site, steps: {"estado": "ok", "texto": next(pages)}  # noqa: E731
    for _ in range(3):
        last = tareas.run_once(t["id"], home=tmp_path, check=check, tell=told.append)
    assert told == ["Cambió colegio: Física: 9; Actualizado 11:01"]
    assert last["estado"] == "listo" and last["hechas"] == 3


def test_a_watched_word_is_told_once(tmp_path):
    told = []
    t = tareas.start(
        "vigilar", "tienda", buscar="disponible", veces=5, home=tmp_path, thread=False
    )
    check = lambda site, steps: {"estado": "ok", "texto": "Producto disponible ya"}  # noqa: E731
    tareas.run_once(t["id"], home=tmp_path, check=check, tell=told.append)
    tareas.run_once(t["id"], home=tmp_path, check=check, tell=told.append)
    assert told == ["Apareció «disponible» en tienda."]


def test_sign_in_needed_and_cancel_and_tick(tmp_path):
    told = []
    t = tareas.start("revisar", "mail", home=tmp_path, thread=False)
    out = tareas.run_once(t["id"], home=tmp_path, tell=told.append,
                          check=lambda s, p: {"estado": "necesita_sesion"})  # fmt: skip
    assert out["estado"] == "error" and "iniciar sesión" in out["error"]
    w = tareas.start("vigilar", "x", home=tmp_path, thread=False)
    tareas.load(tmp_path)
    ran = []
    assert tareas.tick(home=tmp_path, now=w["creada"] + 500, run=ran.append) == [
        w["id"]
    ]
    assert tareas.cancel(w["id"], home=tmp_path)
    assert tareas.get(w["id"], tmp_path)["estado"] == "cancelado"
    assert not tareas.cancel(w["id"], home=tmp_path)
    assert tareas.tick(home=tmp_path, now=w["creada"] + 9999, run=ran.append) == []


def test_fingerprint_ignores_clocks_and_spaces():
    assert tareas.fingerprint("Hola  10:01\nMundo") == tareas.fingerprint(
        "hola 11:59 mundo"
    )
    assert tareas.fingerprint("a") != tareas.fingerprint("b")
