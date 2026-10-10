# HTTP API

Sergio's server (`sergio serve`, or the desktop app) exposes a local HTTP API on
`http://127.0.0.1:8000`. The chat, model and embedding endpoints follow the
OpenAI wire format, so any OpenAI client library works by pointing its base URL
at the server.

- **Interactive reference:** open <http://127.0.0.1:8000/docs> while the server
  runs (Swagger UI generated from the live routes).
- **Machine-readable spec:** [`openapi.json`](openapi.json) (OpenAPI 3.1),
  regenerated with `python scripts/export_openapi.py`.
- **Authentication:** none by default (the server only listens on localhost).
  If it was started with an API key, send `Authorization: Bearer <key>`.
  Requests from a paired phone (`sergio movil`) carry the phone token.

## OpenAI-compatible

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen3:8b", "messages": [{"role": "user", "content": "Hola"}], "stream": false}'
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="local")
reply = client.chat.completions.create(
    model="qwen3:8b", messages=[{"role": "user", "content": "Hola"}]
)
vectors = client.embeddings.create(model="auto", input=["uno", "dos"])
```

| Endpoint | Purpose |
|---|---|
| `POST /v1/chat/completions` | Chat, streaming (`"stream": true`, SSE) or not |
| `GET /v1/models` | Models the engine can serve |
| `POST /v1/embeddings` | Embedding vectors (OpenAI format). `model: "auto"` uses Ollama, then Gemini, then an offline fallback |
| `GET /v1/embeddings/models` | Embedding models available |

## Sergio-specific groups

| Prefix | What it covers |
|---|---|
| `/v1/cowork` | Start a Cowork run, approve or deny steps (`/{id}/decision`), cancel, read the audit trail, follow events (SSE `/{id}/events`) |
| `/v1/evolve/think`, `/v1/evolve/think/stream` | Deep reasoning, as one answer or as a live SSE stream. The same events are available over WebSocket at `/v1/thinking/stream` |
| `/v1/memory` | Long-term memory search and storage |
| `/v1/agents`, `/v1/skills`, `/v1/tasks` | Managed agents, skills and background tasks |
| `/v1/approvals` | Pending approvals (the bell in the app) |
| `/v1/vision`, `/v1/faces` | Camera vision and face recognition (local, with consent) |
| `/v1/speech`, `/v1/voice` | Speech to text and text to speech |
| `/v1/phone`, `/v1/channels` | Calls and messaging channels (owner-only rules apply) |
| `/v1/connectors` | Data sources for Deep Research |
| `/v1/telemetry`, `/v1/savings`, `/metrics` | Usage, energy and cost numbers |
| `/health`, `/v1/info` | Liveness and server information |

WebSocket endpoints (`/v1/thinking/stream` and the agent event stream) are not
part of the OpenAPI file; they are described in the module docstrings under
`src/openjarvis/server/`.
