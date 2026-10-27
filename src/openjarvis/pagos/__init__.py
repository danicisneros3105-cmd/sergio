"""Sergio Pagos: Sergio's own checkout and billing, on top of licensed processors.

The owner (27 Oct 2026): «crea una tipo Stripe, Paddle o PayPal propia
exclusivamente para Sergio… para automatizar todo el proceso». What is
Sergio's own here: the checkout page with Sergio's look, the orders, the
ledger (what came in, the processor's fee, what the AI provider costs, the
margin), the signed notices from each processor and the automation that
follows a payment — the customer's plan and their AI budget
(:mod:`openjarvis.accounts.provision`) switch on by themselves, and switch
back to Free when the month runs out without a renewal.

What is NOT Sergio's and cannot be: moving card money. That needs an
acquiring bank, PCI DSS and money-transmitter licences, so the card is always
typed on the processor's own page (Stripe Checkout, PayPal, or the owner's
self-hosted Hyperswitch — Apache-2.0 — that reaches local processors). Sergio
never sees a card number, and the owner's bank account is entered only in the
processor's dashboard, which pays it out automatically. Only API keys and
webhook secrets go in ``~/.openjarvis/sergio.env``.
"""

from openjarvis.pagos.service import (
    checkout,
    methods,
    order,
    settle,
    summary,
)

__all__ = ["checkout", "methods", "order", "settle", "summary"]
