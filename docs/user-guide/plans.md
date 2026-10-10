# Plans and licenses

Everything that runs on your own computer is free and open source
(Apache 2.0), and will stay that way. Paid plans are services on top.

| Plan | Price | Adds |
|---|---|---|
| **Free** | $0 | The full local assistant: chat, Cowork, plugins, deep reasoning, vision, voice, encrypted backups, sync through your own storage, phone access |
| **Pro** | $12 / month | Hosted sync, premium skills and plugins, early updates |
| **Teams** | $29 / user / month | Multiple users with roles, single sign-on, audit export |
| **Enterprise** | $99 / user / month | On-prem deployment, dedicated support with an SLA |

```bash
sergio planes                     # the plans and the one in force
sergio planes mejorar pro         # opens the payment page
sergio licencia activar <key>
sergio licencia estado
sergio licencia quitar            # back to Free
```

A license is a small Ed25519-signed token
(`sergio-lic-v1.<payload>.<signature>`) holding the plan, seats, holder and
expiry. It is verified offline against the issuer's public key, so checking a
license never contacts a server. When it expires, the device quietly returns
to Free.

Code checks a paid feature with `openjarvis.tiers.has_feature("premium_skills")`
or `require(...)`; anything not listed in `tiers.FEATURES` is free for
everyone.

The seller's side (creating the signing keys, Stripe Payment Links, issuing
licenses) is described in Spanish in
[Planes y licencias](../es/PLANES.md).
