"""What a customer's session may reach. Deny by default.

Sergio is the owner's assistant: his profile, files, PC, connectors, Nodes,
health and memory are his. A customer (an approved account that is not the
owner) gets the chat through their own AI key, the model list, their account,
payments, isolated Cowork tasks and plan-gated Swarm research. Everything else
answers 403. A new customer feature must be added here on purpose.
"""

from __future__ import annotations

ALLOW = {
    ("POST", "/v1/chat/completions"),
    ("GET", "/v1/models"),
    ("GET", "/v1/personal/modelos"),
    ("GET", "/v1/plans"),
    ("GET", "/v1/plans/me"),
    ("GET", "/v1/cowork"),
    ("POST", "/v1/cowork"),
    ("GET", "/v1/swarm"),
    ("POST", "/v1/swarm"),
    ("GET", "/v1/pagos/metodos"),
    ("GET", "/v1/pagos/precio"),
    ("POST", "/v1/pagos/checkout"),
    ("POST", "/v1/pagos/portal"),
    ("GET", "/v1/pagos/referidos"),
    ("POST", "/v1/pagos/referidos"),
}
ALLOW_PREFIX = (
    ("GET", "/v1/pagos/pedido/"),
    ("*", "/v1/cuentas/"),
    ("*", "/v1/cowork/"),
    ("*", "/v1/swarm/"),
)


def allowed(method: str, path: str) -> bool:
    if not (path.startswith("/v1/") or path.startswith("/api/")):
        return True  # the web app's own pages and files
    if (method, path) in ALLOW:
        return True
    if path.startswith("/v1/pagos/pedido/") and path.endswith("/devolver"):
        return False
    return any(
        (m == "*" or m == method) and path.startswith(p) for m, p in ALLOW_PREFIX
    )


def plan_of(uid: str) -> str:
    """The plan a customer has: a paid month in force, else what the owner set."""
    try:
        from openjarvis.pagos import ledger

        paid = ledger.active_plan(uid)
        if paid:
            return paid
    except Exception:  # noqa: BLE001
        pass
    from openjarvis.accounts import provision

    return provision.status(uid).get("plan") or "free"


__all__ = ["ALLOW", "allowed", "plan_of"]
