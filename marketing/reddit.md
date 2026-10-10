# Reddit (borradores)

Diga siempre que es su proyecto. Lea las reglas de cada subreddit el día que
publique (algunos solo permiten autopromoción ciertos días).

## r/LocalLLaMA

**Título:** I built a local-first assistant on top of OpenJarvis: Cowork mode with risk-scored approvals, OpenAI-compatible API, works with any Ollama model

**Texto:**

> Disclosure: this is my project, a fork of Stanford's OpenJarvis (Apache 2.0).
>
> What might interest this sub:
>
> - Runs fully local with Ollama; cloud models are opt-in per task.
> - `/v1/chat/completions`, `/v1/models` and `/v1/embeddings` are
>   OpenAI-compatible, so existing clients just point at `localhost:8000/v1`.
>   Embeddings fall back from Ollama to an offline hashed model when nothing
>   is installed.
> - "Cowork": give it a goal, it plans and executes tool calls, scoring each
>   step on 10 risk axes. Small local models make planning mistakes, so the
>   scrutiny is strict by default and failures make it more careful.
> - Deep-reasoning view that streams each step (draft, critique, revision)
>   over SSE/WebSocket.
>
> Questions for you: which 7–14B models have you found most reliable for
> tool-calling plans? I'm testing qwen3 and gemma variants.

## r/selfhosted

**Título:** Sergio: self-hosted personal assistant with age-encrypted backups to S3/B2/SFTP and zero-knowledge sync between devices

**Texto:**

> Disclosure: my project (fork of OpenJarvis, Apache 2.0).
>
> The self-hosting bits:
>
> - Backups: `sergio respaldo crear` writes incremental tar archives
>   encrypted as standard `age` files (`age -d` opens them without Sergio).
>   Targets: a folder, any S3-compatible bucket (AWS, B2, R2, Wasabi, MinIO)
>   or SFTP with your SSH keys. SQLite is copied with the backup API.
> - Sync: a data key locked with your passphrase lives on your storage;
>   objects are ChaCha20-Poly1305 encrypted under HMAC'd names. Conflicts
>   keep both copies.
> - Phone: a Cloudflare quick tunnel plus a pairing token in the QR
>   fragment; no account, nothing hosted by me.
> - The anonymous usage analytics inherited from upstream are off by
>   default; nothing about your usage leaves the machine unless you turn
>   them on.
>
> Feedback welcome, especially on the sync conflict rules.
