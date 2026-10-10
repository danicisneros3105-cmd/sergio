# Show HN (borrador)

**Título** (máx. 80 caracteres):

> Show HN: Sergio – a local-first personal assistant that works while you're away

**Enlace:** el repositorio público (cuando lo sea).

**Texto:**

> Hi HN. Sergio is a personal AI assistant that runs on your own computer. It's
> a fork of Stanford's OpenJarvis (Apache 2.0) with a Spanish-first interface
> and a few things I wanted for daily use:
>
> - **Cowork mode:** you describe an outcome ("compare three laptops for
>   Blender and make a table") and it plans and runs the steps. Each step is
>   scored on ten risk axes (money, credentials, other people, deletion…);
>   anything risky waits for your approval, it never messages anyone on its
>   own, and every run stops at 50 actions. The log is hash-chained so edits
>   show.
> - **Local models by default** (Ollama), cloud models optional. The chat,
>   models and embeddings endpoints are OpenAI-compatible.
> - **Your data stays yours:** encrypted backups as standard `age` files to a
>   folder, S3/B2 or SFTP, and zero-knowledge sync between your devices
>   through storage you control.
> - **Phone access** without an account: `sergio movil` opens a Cloudflare
>   quick tunnel and shows a QR code that pairs the phone (PWA, works offline
>   for saved answers).
> - **Plugins** as hash-pinned ZIPs with declared permissions; plugins
>   can't send messages or replace built-in tools.
>
> Everything that runs locally is free. I'm considering paid hosted services
> (sync without configuring storage, premium skills) later.
>
> Known limits: it's young, the desktop app targets Windows 11 and Linux/WSL,
> and the quality of answers depends on the model you run.
>
> I'd love feedback on the Cowork approval model in particular: what would
> you need to trust an agent with a two-hour task?
