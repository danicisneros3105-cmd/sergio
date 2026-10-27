"""Automated trading, tested first and always inside limits.

The owner (27 Oct 2026): «que también se pueda automatizar trading con
resultados reales». What Sergio does, honestly:

* **Test before money.** Every strategy is run over years of real daily
  prices first (:func:`backtest`): return, yearly return, worst drop,
  Sharpe, number of trades and the same period just holding the stock. No
  strategy or model can promise gains; the past does not repeat, and Sergio
  says so with every result.
* **Paper first.** Orders go to a broker with an official API (Alpaca:
  stocks and ETFs, paper account by default). Real money only when the
  owner sets ``SERGIO_TRADING_REAL=1`` AND turns on «real» in the settings —
  both, on purpose.
* **Limits that the code enforces**, not the model: the most per order, the
  most per symbol (share of the account), orders per day, the day's loss at
  which everything stops, market hours only, and a stop file
  (``~/.openjarvis/trading/PARAR``) or «Detener» that halts it at once.
  Every order is written to a journal with why it was made.
* The owner's only: customers never reach it (not a financial service;
  managing other people's money needs a licence).

Strategies (classic, documented, no magic): ``cruce_medias`` (20/50-day
moving averages), ``momentum`` (6-month return, with a trend filter) and
``reversion`` (2-day RSI under 10 in an uptrend).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

PAPER = "https://paper-api.alpaca.markets"
LIVE = "https://api.alpaca.markets"
DATA = "https://data.alpaca.markets"
STRATEGIES = ("cruce_medias", "momentum", "reversion")
WARNING = "Resultados pasados no garantizan resultados futuros; se puede perder dinero."


@dataclass
class Limits:
    max_orden_usd: float = 500.0
    max_por_simbolo: float = 0.2  # share of the account in one symbol
    max_ordenes_dia: int = 10
    max_perdida_dia: float = 0.03  # stop for the day at a 3% loss


@dataclass
class Settings:
    activo: bool = False
    real: bool = False
    estrategia: str = "cruce_medias"
    simbolos: List[str] = field(default_factory=lambda: ["SPY", "QQQ"])
    limites: Limits = field(default_factory=Limits)


def _dir(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = get_config_dir()
    d = Path(home) / "trading"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings(home: Optional[Path] = None) -> Settings:
    path = _dir(home) / "ajustes.json"
    if not path.exists():
        return Settings()
    raw = json.loads(path.read_text())
    lim = Limits(
        **{
            k: v
            for k, v in (raw.get("limites") or {}).items()
            if k in Limits.__dataclass_fields__
        }
    )
    return Settings(
        activo=bool(raw.get("activo")),
        real=bool(raw.get("real")),
        estrategia=raw.get("estrategia")
        if raw.get("estrategia") in STRATEGIES
        else "cruce_medias",
        simbolos=[str(s).upper()[:10] for s in raw.get("simbolos") or ["SPY"]][:20],
        limites=lim,
    )


def save_settings(data: Dict[str, Any], home: Optional[Path] = None) -> Settings:
    cur = asdict(settings(home))
    cur.update({k: v for k, v in data.items() if k in cur and k != "limites"})
    if isinstance(data.get("limites"), dict):
        cur["limites"].update(
            {k: v for k, v in data["limites"].items() if k in cur["limites"]}
        )
    (_dir(home) / "ajustes.json").write_text(json.dumps(cur, indent=1))
    return settings(home)


def real_money(s: Settings) -> bool:
    """Real money needs both: the setting and SERGIO_TRADING_REAL=1."""
    return s.real and os.environ.get("SERGIO_TRADING_REAL", "").strip() == "1"


def stopped(home: Optional[Path] = None) -> bool:
    return (_dir(home) / "PARAR").exists()


def stop(on: bool = True, home: Optional[Path] = None) -> None:
    path = _dir(home) / "PARAR"
    if on:
        path.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        path.unlink(missing_ok=True)


# -- signals (pure: closes in, target exposure 0..1 out) ------------------------------------


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1 :] = (c[n:] - c[:-n]) / n
    return out


def _rsi(x: np.ndarray, n: int = 2) -> np.ndarray:
    d = np.diff(x, prepend=x[0])
    up, down = np.clip(d, 0, None), np.clip(-d, 0, None)
    au, ad = _sma(up, n), _sma(down, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(ad == 0, np.inf, au / ad)
    return 100 - 100 / (1 + rs)


def signal(closes: np.ndarray, strategy: str) -> np.ndarray:
    """Exposure wanted at each day's close (1 = in, 0 = out); NaN-free."""
    c = np.asarray(closes, dtype=float)
    if strategy == "cruce_medias":
        fast, slow = _sma(c, 20), _sma(c, 50)
        sig = (fast > slow).astype(float)
    elif strategy == "momentum":
        past = np.roll(c, 126)
        past[:126] = np.nan
        trend = c > _sma(c, 200)
        sig = ((c / past - 1 > 0) & trend).astype(float)
    elif strategy == "reversion":
        rsi, trend = _rsi(c, 2), c > _sma(c, 200)
        sig = np.zeros(len(c))
        holding = False
        for i in range(len(c)):
            if not holding and trend[i] and rsi[i] < 10:
                holding = True
            elif holding and (rsi[i] > 70 or not trend[i]):
                holding = False
            sig[i] = 1.0 if holding else 0.0
    else:
        raise ValueError("estrategia desconocida")
    return np.nan_to_num(sig)


def backtest(
    closes: List[float], strategy: str, cost: float = 0.0005
) -> Dict[str, Any]:
    """The strategy over these daily closes, with no look-ahead (today's
    signal trades tomorrow) and a cost per change of position."""
    c = np.asarray(closes, dtype=float)
    if len(c) < 260:
        raise ValueError("Hacen falta al menos 260 días de precios.")
    ret = np.diff(c) / c[:-1]
    pos = signal(c, strategy)[:-1]  # decided at the close, held the next day
    trades = np.abs(np.diff(pos, prepend=0.0))
    strat = pos * ret - trades * cost
    equity = np.cumprod(1 + strat)
    hold = np.cumprod(1 + ret)
    years = len(ret) / 252

    def drawdown(e: np.ndarray) -> float:
        return float(np.max(1 - e / np.maximum.accumulate(e)))

    sharpe = (
        float(np.mean(strat) / np.std(strat) * np.sqrt(252))
        if np.std(strat) > 0
        else 0.0
    )
    return {
        "estrategia": strategy,
        "dias": int(len(ret)),
        "rentabilidad": round(float(equity[-1] - 1), 4),
        "anual": round(float(equity[-1] ** (1 / years) - 1), 4),
        "peor_caida": round(drawdown(equity), 4),
        "sharpe": round(sharpe, 2),
        "operaciones": int(trades.sum()),
        "tiempo_dentro": round(float(pos.mean()), 3),
        "solo_mantener": round(float(hold[-1] - 1), 4),
        "peor_caida_mantener": round(drawdown(hold), 4),
        "aviso": WARNING,
    }


# -- the broker -------------------------------------------------------------------------------


class Broker:
    """Alpaca's official REST API (paper unless real money is on)."""

    def __init__(self, real: bool = False, http: Any = None) -> None:
        self.base = LIVE if real else PAPER
        self.real = real
        key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
        secret = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
        if not key or not secret:
            raise RuntimeError(
                "Falta ALPACA_API_KEY_ID y ALPACA_API_SECRET_KEY en sergio.env."
            )
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        if http is None:
            import httpx

            http = httpx.Client(timeout=30)
        self.http = http

    def _get(self, url: str, **params: Any) -> Any:
        r = self.http.get(url, headers=self.headers, params=params)
        r.raise_for_status()
        return r.json()

    def account(self) -> Dict[str, Any]:
        return self._get(f"{self.base}/v2/account")

    def clock(self) -> Dict[str, Any]:
        return self._get(f"{self.base}/v2/clock")

    def positions(self) -> Dict[str, float]:
        return {
            p["symbol"]: float(p["market_value"])
            for p in self._get(f"{self.base}/v2/positions")
        }

    def closes(self, symbol: str, days: int = 400) -> List[float]:
        start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 1.5 * 86400))
        data = self._get(f"{DATA}/v2/stocks/{symbol}/bars", timeframe="1Day", start=start, limit=10000,
                         adjustment="all", feed="iex")  # fmt: skip
        return [float(b["c"]) for b in data.get("bars") or []]

    def order(self, symbol: str, notional: float, side: str) -> Dict[str, Any]:
        r = self.http.post(f"{self.base}/v2/orders", headers=self.headers, json={
            "symbol": symbol, "notional": round(notional, 2), "side": side, "type": "market",
            "time_in_force": "day",
        })  # fmt: skip
        r.raise_for_status()
        return r.json()


def _journal(entry: Dict[str, Any], home: Optional[Path] = None) -> None:
    with open(_dir(home) / "diario.jsonl", "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"cuando": time.strftime("%Y-%m-%d %H:%M:%S"), **entry},
                ensure_ascii=False,
            )
            + "\n"
        )


def journal(home: Optional[Path] = None, last: int = 50) -> List[Dict[str, Any]]:
    path = _dir(home) / "diario.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(x)
        for x in path.read_text(encoding="utf-8").splitlines()[-last:]
        if x.strip()
    ]


def run_once(home: Optional[Path] = None, broker: Optional[Broker] = None,
             today: Optional[str] = None) -> Dict[str, Any]:  # fmt: skip
    """One pass: read the signals and bring each symbol toward its target,
    inside every limit. Returns what it did (or why it did nothing)."""
    s = settings(home)
    if not s.activo:
        return {"hecho": [], "nota": "El trading automático está apagado."}
    if stopped(home):
        return {"hecho": [], "nota": "Detenido (archivo PARAR)."}
    real = real_money(s)
    broker = broker or Broker(real=real)
    if not broker.clock().get("is_open"):
        return {"hecho": [], "nota": "La bolsa está cerrada."}
    acc = broker.account()
    equity, last = float(acc.get("equity") or 0), float(acc.get("last_equity") or 0)
    if last and (last - equity) / last >= s.limites.max_perdida_dia:
        stop(True, home)
        _journal(
            {"tipo": "parada", "motivo": "pérdida del día al límite", "equity": equity},
            home,
        )
        return {"hecho": [], "nota": "Se alcanzó la pérdida máxima del día: detenido."}
    day = today or time.strftime("%Y-%m-%d")
    done_today = sum(
        1
        for j in journal(home, 500)
        if j.get("tipo") == "orden" and str(j.get("cuando", "")).startswith(day)
    )
    held = broker.positions()
    did: List[Dict[str, Any]] = []
    for sym in s.simbolos:
        if done_today >= s.limites.max_ordenes_dia:
            break
        closes = broker.closes(sym)
        if len(closes) < 210:
            continue
        want = signal(np.asarray(closes), s.estrategia)[-1]
        target = equity * s.limites.max_por_simbolo * want
        have = held.get(sym, 0.0)
        delta = target - have
        if abs(delta) < max(25.0, 0.02 * equity * s.limites.max_por_simbolo):
            continue  # close enough: no churn
        notional = min(abs(delta), s.limites.max_orden_usd)
        side = "buy" if delta > 0 else "sell"
        try:
            res = broker.order(sym, notional, side)
            why = f"señal {int(want)} con {s.estrategia}; objetivo {target:.0f}, tenía {have:.0f} USD"
            entry = {"tipo": "orden", "simbolo": sym, "lado": side, "usd": round(notional, 2),
                     "real": real, "estrategia": s.estrategia, "id": res.get("id", ""), "por_que": why}  # fmt: skip
        except Exception as exc:  # noqa: BLE001 — written down, next symbol
            entry = {"tipo": "error", "simbolo": sym, "detalle": str(exc)[:200]}
        _journal(entry, home)
        did.append(entry)
        done_today += 1 if entry["tipo"] == "orden" else 0
    return {"hecho": did, "real": real, "nota": WARNING}


def estado(home: Optional[Path] = None) -> Dict[str, Any]:
    s = settings(home)
    return {
        **asdict(s),
        "dinero_real": real_money(s),
        "broker": bool(os.environ.get("ALPACA_API_KEY_ID")),
        "detenido": stopped(home),
        "ultimas": journal(home, 10),
        "aviso": WARNING,
    }


__all__ = [
    "Broker",
    "Limits",
    "STRATEGIES",
    "Settings",
    "WARNING",
    "backtest",
    "estado",
    "journal",
    "real_money",
    "run_once",
    "save_settings",
    "settings",
    "signal",
    "stop",
    "stopped",
]
