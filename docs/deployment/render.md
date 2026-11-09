# Deploy Sergio on Render

`render.yaml` is a production-oriented Blueprint: it builds the React PWA and
FastAPI server into one service, uses a paid `1c-2g` instance, attaches a
persistent disk and deploys only after the linked CI checks pass. Users open the
HTTPS URL in a browser; they do not need to install the desktop app.

## Required operator inputs

Render prompts for every `sync: false` entry. Provide all of them before the
first deployment:

- `OPENROUTER_API_KEY` and `OPENROUTER_MANAGEMENT_KEY`: the owner's inference
  key and the management key used to create capped per-customer subkeys.
- `SERGIO_CLAVE_MAESTRA`: exactly 32 random bytes encoded as base64. Generate it
  locally with `python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"`
  and store it in Render's secret settings, not in Git.
- `SERGIO_PUBLIC_URL`: the final HTTPS URL, without a trailing slash.
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`: use test keys until a complete
  sandbox payment, renewal and cancellation have been verified.
- `SERGIO_SMTP_HOST` and `SERGIO_SMTP_FROM`: the sender used for account
  verification. Add `SERGIO_SMTP_USER`, `SERGIO_SMTP_PASSWORD` and
  `SERGIO_SMTP_PORT` manually when the SMTP service requires them.
- `SERGIO_LEGAL_OPERATOR`, `SERGIO_LEGAL_CONTACT` and
  `SERGIO_LEGAL_JURISDICTION`: public legal identity and contact details. They
  are read from the runtime configuration, not baked into the JavaScript build.

`OPENJARVIS_API_KEY` is generated for the operator's administrative API clients.
Never expose it as `VITE_OPENJARVIS_API_KEY` or store it in a public frontend
build. Browser accounts use their own session tokens instead.

## Stripe webhook

Create a Stripe webhook pointing to
`https://<your-host>/v1/pagos/aviso/stripe` with the events listed in
`docs/PAGOS.md`. Configure Stripe's customer portal as well. A configured key is
not evidence that a payment works: complete the sandbox flow and reconcile the
order, plan activation and ledger before switching to live keys.

## Persistent state and scaling

The disk is mounted at `/home/openjarvis/.openjarvis`, so accounts, encrypted
secrets, tasks and payment state survive restarts and deployments. Render does
not support horizontal scaling for a service with a persistent disk. Keep one
instance; background execution currently depends on that process. A production
launch still needs encrypted backups and a separately tested recovery procedure.

The service waits up to 300 seconds during shutdown. This is a grace period, not
a guarantee that a long task will finish; interrupted work must remain marked as
interrupted rather than being reported as complete.

## Verification before opening registration

1. Push the intended commit and require **CI**, **Frontend CI** and the release
   smoke workflow to pass for that commit.
2. Deploy, check `/health`, then open `/legal/privacidad` and
   `/legal/terminos`; confirm the real operator and contact appear.
3. Test account creation, email verification, login/logout, two-account data
   isolation, plan quotas, a long Cowork task and account deletion.
4. Verify Stripe and OpenRouter in their test modes. Do not make a real charge
   from an automated test.
5. Complete the legal, device, installer-signing and external security review
   items listed by `sergio lanzamiento`.
