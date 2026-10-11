"""The Workspace over HTTP, and the public share page."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi", reason="openjarvis[server] not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server import workspace_routes  # noqa: E402
from openjarvis.workspace import store as store_mod  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(store_mod, "_STORE", None)
    app = FastAPI()
    app.include_router(workspace_routes.router)
    return TestClient(app)


def _page(title="Notas", rev=0):
    now = int(time.time() * 1000)
    return {
        "id": "p_route0001",
        "title": title,
        "parent": None,
        "rev": rev,
        "createdAt": now,
        "updatedAt": now,
        "blocks": [
            {"id": "b_a", "type": "text", "text": "hola mundo"},
            {
                "id": "b_i",
                "type": "image",
                "text": "",
                "media": {"file": "", "name": "x"},
            },
        ],
    }


def test_pages_round_trip_with_conflicts(client):
    r = client.put(
        "/v1/workspace/pages/p_route0001", json={"page": _page(), "base_rev": 0}
    )
    assert r.status_code == 200 and r.json()["page"]["rev"] == 1
    assert client.get("/v1/workspace/pages").json()["pages"][0]["title"] == "Notas"
    assert (
        client.get("/v1/workspace/pages/p_route0001").json()["page"]["blocks"][0][
            "text"
        ]
        == "hola mundo"
    )
    assert (
        client.put(
            "/v1/workspace/pages/p_route0001",
            json={"page": _page("Nuevo"), "base_rev": 1},
        ).status_code
        == 200
    )
    stale = client.put(
        "/v1/workspace/pages/p_route0001", json={"page": _page("Viejo"), "base_rev": 1}
    )
    assert (
        stale.status_code == 409
        and stale.json()["page"]["title"] == "Nuevo"
        and stale.json()["copy"].startswith("p_")
    )
    assert (
        client.put(
            "/v1/workspace/pages/p_other0001", json={"page": _page()}
        ).status_code
        == 400
    )
    assert client.get("/v1/workspace/pages/p_missing01").status_code == 404
    assert client.get("/v1/workspace/pages/..%2F..%2Fx").status_code in (400, 404)
    found = {
        r["id"]
        for r in client.get("/v1/workspace/search", params={"q": "mundo"}).json()[
            "results"
        ]
    }
    assert (
        "p_route0001" in found and stale.json()["copy"] in found
    )  # the conflict copy is findable too
    assert (
        client.get("/v1/workspace/export").headers["content-type"] == "application/zip"
    )
    assert client.delete("/v1/workspace/pages/p_route0001").json() == {"deleted": True}


def test_files_and_a_share_that_shows_only_its_part(client):
    up = client.post(
        "/v1/workspace/files", files={"file": ("nota.webm", b"WEBM", "audio/webm")}
    )
    assert up.status_code == 200
    file_id = up.json()["file"]
    assert client.get(f"/v1/workspace/files/{file_id}").content == b"WEBM"
    assert (
        client.post(
            "/v1/workspace/files",
            files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
        ).status_code
        == 400
    )
    page = _page()
    page["blocks"].append(
        {
            "id": "b_audio",
            "type": "audio",
            "text": "",
            "media": {"file": file_id, "name": "nota"},
        }
    )
    page["blocks"].append({"id": "b_priv", "type": "text", "text": "solo para mí"})
    client.put("/v1/workspace/pages/p_route0001", json={"page": page})
    share = client.post(
        "/v1/workspace/shares",
        json={"page": "p_route0001", "scope": "block", "block": "b_audio"},
    ).json()
    assert share["url"].endswith(share["path"])
    public = client.get(share["path"])
    assert (
        public.status_code == 200
        and "solo para mí" not in public.text
        and "<audio" in public.text
    )
    assert "default-src 'none'" in public.headers["content-security-policy"]
    assert client.get(f"{share['path']}/files/{file_id}").content == b"WEBM"
    other = client.post(
        "/v1/workspace/files", files={"file": ("b.png", b"PNG", "image/png")}
    ).json()["file"]
    assert (
        client.get(f"{share['path']}/files/{other}").status_code == 404
    )  # not in the shared part
    assert (
        len(
            client.get("/v1/workspace/shares", params={"page": "p_route0001"}).json()[
                "shares"
            ]
        )
        == 1
    )
    assert client.delete(f"/v1/workspace/shares/{share['token']}").json() == {
        "revoked": True
    }
    assert client.get(share["path"]).status_code == 404
    assert client.get("/s/not-a-real-token-at-all-xxxxxx").status_code == 404
    bad = client.post(
        "/v1/workspace/shares",
        json={
            "page": "p_route0001",
            "scope": "rows",
            "block": "b_audio",
            "rows": ["r"],
        },
    )
    assert bad.status_code == 400
