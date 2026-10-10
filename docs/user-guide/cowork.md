# Cowork mode

Describe the outcome you want, step away, and Sergio does the work: it plans
the steps, runs the safe ones on its own and asks you about the rest.

```bash
sergio cowork "compare the 3 best laptops for Blender and make me a table"
sergio cowork lista               # runs, newest first
sergio cowork estado <id>         # steps and their status
sergio cowork aprobar <id> 3      # approve step 3
sergio cowork rechazar <id> 3
sergio cowork cancelar <id>
sergio cowork auditoria <id>      # the tamper-evident log
```

The app has a **Cowork** page with the same controls, and approvals also
appear in the bell. With the server running, a run keeps going if you close
the terminal.

## How Sergio decides what to ask

Before every step, Sergio scores it from 0 to 3 on ten axes:

| Axis | Examples |
|---|---|
| `privacy` | reads personal data |
| `destructive` | deletes or overwrites files |
| `external_actor` | contacts or acts towards other people |
| `financial` | payments, purchases |
| `credentials` | passwords, keys, tokens |
| `system` | changes system settings |
| `network` | uploads or downloads |
| `irreversible` | cannot be undone |
| `scope` | touches much more than the goal needs |
| `uncertainty` | the plan is unsure what the step does |

The `autonomy` setting decides how high a score may run without asking:
`cauteloso` asks about anything that scores, `normal` allows 1, `autonomo`
allows 2. Some rules hold at every level:

- money, credentials and anything aimed at other people **always ask**;
- sending messages, calling or posting is never planned at all;
- a step you approved three times with the same signature is trusted, and
  one you denied twice is blocked;
- two failures in a row make the run more careful for the rest of it.

Every run stops at `max_actions` (50 by default, at most 500). Unanswered
approvals count as "no" after `approval_timeout_minutes`.

## Audit trail

Each step, decision and result is appended to a log where every entry carries
the SHA-256 of the previous one, so an edited or deleted entry breaks the
chain and `sergio cowork auditoria` reports it. Secrets are masked before they
are written.

## Configuration

```toml
[cowork]
max_actions = 50
autonomy = "normal"            # cauteloso | normal | autonomo
approval_timeout_minutes = 120
notify_channel = ""            # e.g. "telegram"; empty = app and CLI only
notify_to = ""                 # your own id on that channel
```

Progress notifications only go to you: phone channels accept only the numbers
listed in `[phone] owner_numbers`.

## API

`POST /v1/cowork` starts a run; `GET /v1/cowork/{id}/events` streams its
progress (SSE); `POST /v1/cowork/{id}/decision` answers an approval. See the
[HTTP API](../api/index.md).
