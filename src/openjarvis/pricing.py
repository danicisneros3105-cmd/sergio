"""Prices in each country's currency.

The rule the owner set (oct. 2026): a plan costs its US-dollar price, or the
equivalent in the local currency, and **never less than the dollar price**.

* Go (5 dollars) in a currency worth more than the dollar (euro, pound, Swiss
  franc...) shows the same number: Go is 5 euros, not 4.30. The bigger plans
  are the exact conversion rounded up.
* A currency worth less shows the dollar price converted and rounded **up** to
  a clean amount (Go in Mexico: 90 pesos when 5 dollars are 87).
* Countries that use the dollar (Ecuador, El Salvador, Panama...) pay dollars.

Rates change every day. ``RATES`` is a recent snapshot; with network the
rates are refreshed once a day from the European Central Bank's published
rates (via frankfurter.dev) and kept in ``~/.openjarvis/divisas.json``. The
amount charged is always the one the payment page confirms.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

RATES_DATE = "2026-10-22"
# Units of each currency per 1 US dollar (a snapshot; see the module note).
RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.86,
    "GBP": 0.75,
    "CHF": 0.80,
    "CAD": 1.38,
    "AUD": 1.52,
    "NZD": 1.68,
    "JPY": 152.0,
    "CNY": 7.15,
    "KRW": 1420.0,
    "INR": 88.0,
    "SGD": 1.31,
    "HKD": 7.78,
    "SEK": 9.6,
    "NOK": 10.1,
    "DKK": 6.4,
    "PLN": 3.7,
    "CZK": 21.5,
    "HUF": 345.0,
    "RON": 4.3,
    "TRY": 42.0,
    "ILS": 3.4,
    "AED": 3.67,
    "SAR": 3.75,
    "ZAR": 18.0,
    "NGN": 1500.0,
    "EGP": 48.0,
    "KES": 129.0,
    "MXN": 18.3,
    "BRL": 5.4,
    "ARS": 1450.0,
    "CLP": 940.0,
    "COP": 3950.0,
    "PEN": 3.5,
    "UYU": 40.0,
    "BOB": 6.9,
    "PYG": 7500.0,
    "CRC": 510.0,
    "GTQ": 7.7,
    "HNL": 26.0,
    "NIO": 36.8,
    "DOP": 62.0,
    "VES": 250.0,
    "THB": 33.5,
    "VND": 25400.0,
    "IDR": 16300.0,
    "MYR": 4.3,
    "PHP": 58.0,
    "PKR": 280.0,
    "BDT": 122.0,
    "UAH": 41.5,
    "RUB": 92.0,
    "MAD": 9.3,
}

SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥", "KRW": "₩", "INR": "₹",
    "BRL": "R$", "MXN": "$", "ARS": "$", "CLP": "$", "COP": "$", "UYU": "$", "CAD": "$",
    "AUD": "$", "NZD": "$", "SGD": "$", "HKD": "$", "CHF": "CHF ", "PEN": "S/", "TRY": "₺",
    "PLN": "zł", "ILS": "₪", "UAH": "₴", "PHP": "₱", "VND": "₫", "THB": "฿", "NGN": "₦",
}  # fmt: skip

# Countries that pay in US dollars (their own money is the dollar).
USD_COUNTRIES = {
    "US",
    "EC",
    "SV",
    "PA",
    "PR",
    "GU",
    "VI",
    "AS",
    "MP",
    "TL",
    "ZW",
    "FM",
    "MH",
    "PW",
}
EURO_COUNTRIES = {
    "AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT", "LV", "LT", "LU",
    "MT", "NL", "PT", "SK", "SI", "ES", "AD", "MC", "SM", "VA", "ME", "XK",
}  # fmt: skip
COUNTRY_CURRENCY: Dict[str, str] = {
    "GB": "GBP", "CH": "CHF", "LI": "CHF", "CA": "CAD", "AU": "AUD", "NZ": "NZD", "JP": "JPY",
    "CN": "CNY", "KR": "KRW", "IN": "INR", "SG": "SGD", "HK": "HKD", "SE": "SEK", "NO": "NOK",
    "DK": "DKK", "PL": "PLN", "CZ": "CZK", "HU": "HUF", "RO": "RON", "TR": "TRY", "IL": "ILS",
    "AE": "AED", "SA": "SAR", "ZA": "ZAR", "NG": "NGN", "EG": "EGP", "KE": "KES", "MX": "MXN",
    "BR": "BRL", "AR": "ARS", "CL": "CLP", "CO": "COP", "PE": "PEN", "UY": "UYU", "BO": "BOB",
    "PY": "PYG", "CR": "CRC", "GT": "GTQ", "HN": "HNL", "NI": "NIO", "DO": "DOP", "VE": "VES",
    "TH": "THB", "VN": "VND", "ID": "IDR", "MY": "MYR", "PH": "PHP", "PK": "PKR", "BD": "BDT",
    "UA": "UAH", "RU": "RUB", "MA": "MAD",
}  # fmt: skip
COUNTRY_NAMES = {
    "EC": "Ecuador", "US": "Estados Unidos", "MX": "México", "CO": "Colombia", "PE": "Perú",
    "AR": "Argentina", "CL": "Chile", "BR": "Brasil", "UY": "Uruguay", "BO": "Bolivia",
    "PY": "Paraguay", "VE": "Venezuela", "CR": "Costa Rica", "PA": "Panamá", "GT": "Guatemala",
    "HN": "Honduras", "NI": "Nicaragua", "SV": "El Salvador", "DO": "República Dominicana",
    "ES": "España", "FR": "Francia", "DE": "Alemania", "IT": "Italia", "PT": "Portugal",
    "NL": "Países Bajos", "BE": "Bélgica", "AT": "Austria", "IE": "Irlanda", "FI": "Finlandia",
    "GR": "Grecia", "GB": "Reino Unido", "CH": "Suiza", "SE": "Suecia", "NO": "Noruega",
    "DK": "Dinamarca", "PL": "Polonia", "CZ": "Chequia", "RO": "Rumanía", "HU": "Hungría",
    "TR": "Turquía", "UA": "Ucrania", "RU": "Rusia", "CA": "Canadá", "AU": "Australia",
    "NZ": "Nueva Zelanda", "JP": "Japón", "CN": "China", "KR": "Corea del Sur", "IN": "India",
    "SG": "Singapur", "HK": "Hong Kong", "TH": "Tailandia", "VN": "Vietnam", "ID": "Indonesia",
    "MY": "Malasia", "PH": "Filipinas", "PK": "Pakistán", "BD": "Bangladés", "IL": "Israel",
    "AE": "Emiratos Árabes", "SA": "Arabia Saudita", "ZA": "Sudáfrica", "NG": "Nigeria",
    "EG": "Egipto", "KE": "Kenia", "MA": "Marruecos",
}  # fmt: skip


def country_currency(country: str) -> str:
    """The currency a country pays in (dollars when unknown)."""
    country = str(country or "").strip().upper()
    if country in USD_COUNTRIES:
        return "USD"
    if country in EURO_COUNTRIES:
        return "EUR"
    return COUNTRY_CURRENCY.get(country, "USD")


# -- rates ---------------------------------------------------------------------


def _cache_path() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "divisas.json"


def rates(*, refresh: bool = False, now: Optional[float] = None) -> Dict[str, Any]:
    """``{"date", "rates", "live"}``: today's rates when known, else the snapshot."""
    now = now or time.time()
    try:
        saved = json.loads(_cache_path().read_text("utf-8"))
    except (OSError, ValueError):
        saved = {}
    if (
        isinstance(saved, dict)
        and saved.get("rates")
        and now - float(saved.get("fetched", 0)) < 86400
        and not refresh
    ):
        return {"date": saved["date"], "rates": saved["rates"], "live": True}
    if refresh and not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            with urllib.request.urlopen(
                "https://api.frankfurter.dev/v1/latest?base=USD", timeout=6
            ) as resp:
                data = json.load(resp)
            live = {k: float(v) for k, v in data["rates"].items()}
            live["USD"] = 1.0
            merged = {
                **RATES,
                **live,
            }  # the ones the bank does not publish keep the snapshot
            _cache_path().write_text(
                json.dumps(
                    {"date": data.get("date", ""), "rates": merged, "fetched": now}
                ),
                encoding="utf-8",
            )
            return {"date": data.get("date", ""), "rates": merged, "live": True}
        except Exception:  # noqa: BLE001 — offline: the snapshot is still honest
            pass
    return {"date": RATES_DATE, "rates": RATES, "live": False}


# -- amounts -------------------------------------------------------------------


def _step(amount: float) -> int:
    """A clean step to round a price up to (1, 5, 10, 50, 100...)."""
    if amount < 50:
        return 1
    if amount < 500:
        return 5
    if amount < 5000:
        return 10
    if amount < 50000:
        return 100
    return 1000


def local_amount(
    usd: float, currency: str, table: Optional[Dict[str, float]] = None
) -> int:
    """What *usd* dollars cost in *currency*: never below the dollar price, and
    rounded up to a clean amount."""
    if usd <= 0:
        return 0
    currency = currency.upper()
    rate = (table or RATES).get(currency)
    if currency == "USD" or rate is None:
        return math.ceil(usd)
    if rate <= 1:
        # A currency worth more than the dollar. The entry plan (5 dollars) keeps
        # the same number, as the owner decided: Go is 5 euros. The bigger plans
        # are the exact conversion rounded up (Work 21 dollars: 19 euros).
        if usd <= 5:
            return math.ceil(usd)
        return math.ceil(usd * rate)
    exact = usd * rate
    step = _step(exact)
    return int(math.ceil(exact / step) * step)


def format_amount(amount: int, currency: str) -> str:
    currency = currency.upper()
    symbol = SYMBOLS.get(currency, f"{currency} ")
    text = f"{amount:,}".replace(
        ",", " " if currency not in {"USD", "GBP", "AUD", "CAD"} else ","
    )
    if currency in {"EUR", "PLN", "CZK", "SEK", "NOK", "DKK", "HUF", "RON"}:
        return f"{text} {symbol}".strip()
    return f"{symbol}{text}"


def price_for(
    usd: float, country: str, table: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    currency = country_currency(country)
    amount = local_amount(usd, currency, table)
    return {
        "usd": usd,
        "currency": currency,
        "amount": amount,
        "text": format_amount(amount, currency) if usd else "0",
    }


__all__ = [
    "COUNTRY_NAMES",
    "country_currency",
    "format_amount",
    "local_amount",
    "price_for",
    "rates",
]
