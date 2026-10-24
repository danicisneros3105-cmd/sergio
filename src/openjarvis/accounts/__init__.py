"""Accounts: sign in and sign up for Sergio, safely.

* **Email and password** — the password is stretched with scrypt and never
  stored; the email is confirmed with a six-digit code.
* **Google, Microsoft, Apple** — OpenID Connect with PKCE (:mod:`oauth`);
  the id_token signature is checked against the provider's keys.
* **Phone** — a code by SMS (Twilio Verify when configured).
* **Fraud** (:mod:`fraud`) — throwaway mail domains are refused
  (:mod:`disposable`), the same inbox written another way (dots, +tags,
  googlemail) is the same person, and too many accounts from one device or
  network, or a phone already used, is stopped or held for review.

Sergio is personal: the first account, made on the computer itself, is the
owner's. Every other account waits until the owner approves it, so nobody
reaches Sergio just by signing up.
"""

from openjarvis.accounts.store import AccountStore, get_store

__all__ = ["AccountStore", "get_store"]
