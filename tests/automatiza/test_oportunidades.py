"""Clients and jobs: sources parsed, scored against his profile, drafts
written — and nothing ever sent."""

from __future__ import annotations

import json

from openjarvis.automatiza import oportunidades as op


class R:
    def __init__(self, data=None, text=""):
        self._d, self.text, self.status_code = data, text, 200

    def json(self):
        return self._d

    def raise_for_status(self):
        return None


def test_remoteok_skips_the_legal_notice_row():
    rows = [
        {"legal": "notice"},
        {
            "position": "Editor de video",
            "company": "ACME",
            "url": "https://remoteok.com/1",
            "tags": ["video"],
            "description": "<p>Edita</p>",
        },
    ]
    got = op.remoteok(get=lambda *a, **k: R(rows))
    assert (
        len(got) == 1
        and got[0]["titulo"] == "Editor de video"
        and got[0]["tipo"] == "trabajo"
    )


def test_weworkremotely_rss_is_parsed_without_entities():
    rss = """<?xml version="1.0"?><rss><channel><item><title>ACME: Video Editor</title>
    <link>https://weworkremotely.com/x</link><description>Edit &amp; cut</description></item></channel></rss>"""
    got = op.weworkremotely(get=lambda *a, **k: R(text=rss))
    assert got and got[0]["empresa"] == "ACME" and "Video Editor" in got[0]["titulo"]


def test_score_prefers_what_matches_his_skills():
    prof = {
        "habilidades": ["edición de video", "premiere"],
        "idiomas": ["español"],
        "remoto": True,
    }
    good = {
        "titulo": "Editor de video Premiere",
        "texto": "edición de video remoto",
        "etiquetas": ["video"],
    }
    bad = {"titulo": "Contador senior", "texto": "impuestos", "etiquetas": []}
    assert op.score(good, prof) > op.score(bad, prof)


def test_hunt_saves_new_items_with_drafts_and_sends_nothing(tmp_path, monkeypatch):
    op.save_profile(
        {"busco": "empleo", "habilidades": ["video"], "sobre_mi": "Editor"}, tmp_path
    )
    # No «lugar» nor «texto»: a draft is written anyway (it used to fail silently).
    job = {
        "tipo": "trabajo",
        "titulo": "Video editor",
        "empresa": "A",
        "url": "https://a.example/1",
        "etiquetas": ["video"],
    }
    sent = []
    monkeypatch.setattr(
        "httpx.post", lambda *a, **k: sent.append(a) or R({}), raising=False
    )
    out = op.hunt(tmp_path, sources={"fake": lambda: [job, dict(job)]}, search=lambda q, n: [],
                  ask=lambda p, **k: "Hola, soy editor…")  # fmt: skip
    rows = op.items(tmp_path)
    assert len(rows) == 1  # the same link once
    assert rows[0]["borrador"].startswith("Hola") and rows[0]["estado"] == "borrador"
    assert sent == []
    assert isinstance(out, dict)
    op.hunt(
        tmp_path,
        sources={"fake": lambda: [job]},
        search=lambda q, n: [],
        ask=lambda p, **k: "otro",
    )
    assert len(op.items(tmp_path)) == 1  # never duplicated on the next day


def test_empleo_from_the_page_means_jobs(tmp_path):
    assert op.save_profile({"busco": "empleo"}, tmp_path)["busco"] == "trabajo"


def test_states_are_his_to_set(tmp_path):
    op._save([{"id": "x", "estado": "nueva"}], tmp_path)
    assert op.set_state("x", "enviada", tmp_path)
    assert op.items(tmp_path)[0]["estado"] == "enviada"
    try:
        op.set_state("x", "hackeado", tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown state must be refused")
    json.dumps(op.items(tmp_path))
