"""POST /v1/embeddings: OpenAI-compatible, three providers, auto choice."""

from __future__ import annotations

import base64
import math
import struct

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server import embeddings_routes as er  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(er, "ollama_embedding_models", lambda timeout=2.0: [])
    app = FastAPI()
    app.include_router(er.router)
    return TestClient(app)


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_local_model_shape_and_similarity(client):
    resp = client.post(
        "/v1/embeddings",
        json={
            "model": "sergio-local",
            "input": [
                "la tetera está rota",
                "comprar una tetera nueva",
                "mercado de valores",
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "list" and body["model"] == "sergio-local"
    vecs = [d["embedding"] for d in body["data"]]
    assert [d["index"] for d in body["data"]] == [0, 1, 2]
    assert all(abs(math.sqrt(sum(v * v for v in vec)) - 1) < 1e-6 for vec in vecs)
    assert _cos(vecs[0], vecs[1]) > _cos(vecs[0], vecs[2])
    assert body["usage"]["prompt_tokens"] > 0


def test_auto_falls_back_to_local_without_ollama_or_key(client):
    body = client.post("/v1/embeddings", json={"input": "hola"}).json()
    assert body["model"] == "sergio-local"


def test_dimensions_and_base64(client):
    body = client.post(
        "/v1/embeddings",
        json={
            "model": "sergio-local",
            "input": "hola mundo",
            "dimensions": 64,
            "encoding_format": "base64",
        },
    ).json()
    raw = base64.b64decode(body["data"][0]["embedding"])
    vec = struct.unpack("<64f", raw)
    assert len(vec) == 64 and abs(math.sqrt(sum(v * v for v in vec)) - 1) < 1e-5


@pytest.mark.parametrize(
    "payload",
    [
        {"input": ""},
        {"input": []},
        {"input": ["ok", " "]},
        {"input": "x", "encoding_format": "hex"},
        {"input": "x", "dimensions": 2},
        {"input": ["x"] * (er.MAX_INPUTS + 1)},
    ],
)
def test_bad_requests(client, payload):
    assert client.post("/v1/embeddings", json=payload).status_code == 400


def test_gemini_needs_a_key(client):
    resp = client.post(
        "/v1/embeddings", json={"model": "gemini-embedding-001", "input": "x"}
    )
    assert resp.status_code == 404 and "GEMINI_API_KEY" in resp.json()["detail"]


def test_ollama_model_is_used_and_preferred_by_auto(client, monkeypatch):
    seen = {}

    def fake_ollama(texts, model):
        seen["model"] = model
        return [[3.0, 4.0] for _ in texts]

    monkeypatch.setattr(er, "embed_ollama", fake_ollama)
    monkeypatch.setattr(
        er,
        "ollama_embedding_models",
        lambda timeout=2.0: ["mxbai-embed-large:latest", "nomic-embed-text:latest"],
    )
    body = client.post("/v1/embeddings", json={"input": ["a", "b"]}).json()
    assert (
        body["model"] == "nomic-embed-text:latest"
        and seen["model"] == "nomic-embed-text:latest"
    )
    assert body["data"][0]["embedding"] == [3.0, 4.0]


def test_ollama_missing_model_is_404(client, monkeypatch):
    def missing(texts, model):
        raise LookupError(
            f"Ollama does not have the model {model!r}. Pull it with: ollama pull {model}"
        )

    monkeypatch.setattr(er, "embed_ollama", missing)
    resp = client.post("/v1/embeddings", json={"model": "bge-m3", "input": "x"})
    assert resp.status_code == 404 and "ollama pull bge-m3" in resp.json()["detail"]


def test_provider_failure_is_502(client, monkeypatch):
    def down(texts, model):
        raise ConnectionError("refused")

    monkeypatch.setattr(er, "embed_ollama", down)
    assert (
        client.post(
            "/v1/embeddings", json={"model": "nomic-embed-text", "input": "x"}
        ).status_code
        == 502
    )


def test_real_ollama_http_contract(monkeypatch):
    respx = pytest.importorskip("respx")
    import httpx

    monkeypatch.setenv("OLLAMA_HOST", "http://ollama.test:11434")
    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://ollama.test:11434/api/embed").mock(
            return_value=httpx.Response(
                200, json={"embeddings": [[0.0, 2.0], [1.0, 0.0]]}
            )
        )
        assert er.embed_ollama(["a", "b"], "nomic-embed-text") == [
            [0.0, 1.0],
            [1.0, 0.0],
        ]
        mock.post("http://ollama.test:11434/api/embed").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(LookupError, match="ollama pull"):
            er.embed_ollama(["a"], "nope")


def test_models_listing(client):
    body = client.get("/v1/embeddings/models").json()
    ids = {m["id"]: m for m in body["data"]}
    assert ids["sergio-local"]["available"] is True
    assert ids["gemini-embedding-001"]["available"] is False
    assert body["auto"] == "sergio-local"


def test_openai_client_compatibility(client):
    openai = pytest.importorskip("openai")
    import httpx

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=client.post(
                "/v1/embeddings",
                content=request.content,
                headers={"content-type": "application/json"},
            ).json(),
        )
    )
    oc = openai.OpenAI(
        api_key="x",
        base_url="http://sergio.test/v1",
        http_client=httpx.Client(transport=transport),
    )
    out = oc.embeddings.create(model="sergio-local", input=["hola"])
    assert len(out.data[0].embedding) == 1024
