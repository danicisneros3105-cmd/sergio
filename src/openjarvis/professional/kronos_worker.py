"""Separate optional PyTorch runtime. Loads only pinned code and local weights."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    root, source = map(Path, sys.argv[1:])
    sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if sha != "67b630e67f6a18c9e9be918d9b4337c960db1e9a":
        raise ValueError("Kronos source revision is not the reviewed revision")
    if subprocess.check_output(
        ["git", "-C", str(root), "diff", "--name-only", "HEAD", "--", "model"],
        text=True,
    ).strip():
        raise ValueError("Kronos model source was modified")
    import pandas as pd
    import torch

    torch.set_num_threads(2)
    torch.manual_seed(0)
    sys.path.insert(0, str(root))
    from model import Kronos, KronosPredictor, KronosTokenizer

    data = json.loads(source.read_text(encoding="utf-8"))
    frame = pd.DataFrame(data["rows"])
    model = Kronos.from_pretrained(str(root / "weights/model"), local_files_only=True)
    tokenizer = KronosTokenizer.from_pretrained(
        str(root / "weights/tokenizer"), local_files_only=True
    )
    model.eval()
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
    with torch.inference_mode():
        predicted = predictor.predict(
            df=frame[["open", "high", "low", "close", "volume", "amount"]],
            x_timestamp=pd.to_datetime(frame.timestamp, utc=True).dt.tz_localize(None),
            y_timestamp=pd.Series(
                pd.to_datetime(data["future"], utc=True).tz_localize(None)
            ),
            pred_len=len(data["future"]),
            T=1.0,
            top_p=0.9,
            sample_count=3,
            verbose=False,
        )
    print("SERGIO_KRONOS " + predicted.to_json(orient="records"))


if __name__ == "__main__":
    main()


__all__ = ["main"]
