"""Throwaway mail domains (temp mail) refused at sign-up.

A seed of the most used ones ships here; the full public list
(disposable-email-domains, CC0, several thousand domains) is downloaded to
``~/.openjarvis/cuentas/desechables.txt`` by ``sergio cuentas listas`` (the
update script runs it). Subdomains of a listed domain count too.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import FrozenSet, Optional

LIST_URL = (
    "https://raw.githubusercontent.com/disposable-email-domains/"
    "disposable-email-domains/main/disposable_email_blocklist.conf"
)

SEED = frozenset(
    """
0-mail.com 10minutemail.com 10minutemail.net 10minutemail.co.uk 20minutemail.com 33mail.com
anonbox.net anonymbox.com burnermail.io byom.de dispostable.com dropmail.me
emailondeck.com emailtemporanea.com emailtemporario.com.br fakeinbox.com fakemail.net
getairmail.com getnada.com guerrillamail.com guerrillamail.net guerrillamail.org guerrillamail.biz
guerrillamailblock.com grr.la harakirimail.com inboxbear.com incognitomail.org jetable.org
mail-temp.com mailcatch.com maildrop.cc mailinator.com mailinator.net mailinator2.com mailnesia.com
mailpoof.com mailsac.com mailtemp.net mintemail.com moakt.com mohmal.com mytemp.email
nada.email nwldx.com sharklasers.com spam4.me spamgourmet.com spambox.us temp-mail.org
temp-mail.io tempail.com tempemail.net tempinbox.com tempmail.com tempmail.net tempmail.plus
tempmailo.com tempr.email throwawaymail.com tmail.ws tmpmail.net tmpmail.org trashmail.com
trashmail.de trashmail.net yopmail.com yopmail.fr yopmail.net emailfake.com fakemailgenerator.com
mailforspam.com spamex.com tempmailaddress.com 1secmail.com 1secmail.net 1secmail.org
dropmail.com minuteinbox.com luxusmail.org emltmp.com etempmail.net tempmail.dev inboxkitten.com
mail.tm mailto.plus fexpost.com fexbox.org rover.info chitthi.in disposablemail.com
""".split()
)


def list_path() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "cuentas" / "desechables.txt"


@lru_cache(maxsize=1)
def _domains(path: Optional[str] = None) -> FrozenSet[str]:
    p = Path(path) if path else list_path()
    try:
        extra = {
            line.strip().lower()
            for line in p.read_text("utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    except OSError:
        extra = set()
    return SEED | frozenset(extra)


def is_disposable(domain: str) -> bool:
    d = (domain or "").strip().lower().rstrip(".")
    known = _domains()
    parts = d.split(".")
    return any(".".join(parts[i:]) in known for i in range(len(parts) - 1))


def update_list(fetch=None) -> int:
    """Download the full list (CC0). Returns how many domains it has."""
    if fetch is None:
        import httpx

        def fetch(url: str) -> str:
            with httpx.Client(timeout=60, follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                return r.text

    text = fetch(LIST_URL)
    domains = [
        x.strip().lower()
        for x in text.splitlines()
        if "." in x and not x.startswith("#")
    ]
    if len(domains) < 100:
        raise ValueError("la lista llegó vacía o rota; se queda la anterior")
    p = list_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_text("\n".join(sorted(set(domains))) + "\n", "utf-8")
    tmp.replace(p)
    _domains.cache_clear()
    return len(set(domains))


__all__ = ["LIST_URL", "SEED", "is_disposable", "update_list"]
