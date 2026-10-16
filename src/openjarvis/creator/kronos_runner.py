"""Runs one Kronos forecast in Kronos' own Python (torch lives there, not in
Sergio's). Reads a JSON request on stdin, writes one JSON line on stdout.

Started by ``openjarvis.creator.kronos`` as
``<kronos venv>/python -I kronos_runner.py`` with the Kronos repository
folder in the request; it imports nothing from Sergio.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    req = json.load(sys.stdin)
    sys.path.insert(0, req["repo"])
    import pandas as pd
    from model import Kronos, KronosPredictor, KronosTokenizer  # Kronos' own package

    tokenizer = KronosTokenizer.from_pretrained(req["tokenizer"])
    model = Kronos.from_pretrained(req["model"])
    predictor = KronosPredictor(
        model,
        tokenizer,
        device=req.get("device") or "cpu",
        max_context=int(req["max_context"]),
    )
    rows = req["rows"]
    df = pd.DataFrame(rows)
    x = df[["open", "high", "low", "close", "volume"]].astype(float)
    x_ts = pd.Series(pd.to_datetime(df["date"]))
    y_ts = pd.Series(pd.to_datetime(req["future"]))
    out = predictor.predict(
        df=x,
        x_timestamp=x_ts,
        y_timestamp=y_ts,
        pred_len=len(y_ts),
        T=float(req.get("temperature", 1.0)),
        top_p=float(req.get("top_p", 0.9)),
        sample_count=int(req.get("samples", 1)),
        verbose=False,
    )
    forecast = [
        {
            "date": str(day)[:10],
            **{
                k: round(float(out.iloc[i][k]), 4)
                for k in ("open", "high", "low", "close", "volume")
            },
        }
        for i, day in enumerate(req["future"])
    ]
    sys.stdout.write(json.dumps({"forecast": forecast}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
