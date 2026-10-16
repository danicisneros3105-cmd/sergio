#!/usr/bin/env python3
"""Public connectivity checks; --live opts into network, never into account access.

An OAuth discovery success is NOT a completed account connection. No tokens,
registrations, tool executions or personal account data are requested here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openjarvis.mcp import oauth  # noqa: E402
from openjarvis.mcp.directory import directory  # noqa: E402


def check(entry):
    import httpx

    deadline = time.monotonic() + 20

    class DeadlineClient(httpx.Client):
        def request(self, *args, **kwargs):
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("Public check budget exhausted")
            kwargs["timeout"] = min(left, 5.0)
            return super().request(*args, **kwargs)

    result = {"id": entry["id"], "url": entry["url"], "account_verified": False}
    try:
        with DeadlineClient(timeout=5.0) as http:
            challenge = oauth.probe(http, entry["url"])
            if challenge is not None or entry.get("requires_client_id"):
                auth = oauth.discover(http, entry["url"], challenge or {})
                result.update(
                    status="oauth_available"
                    if auth.metadata_verified
                    else "oauth_fallback_unverified",
                    issuer=auth.issuer,
                    requires_client_id=not bool(auth.registration_endpoint),
                )
            else:
                result["status"] = "initialize_response_only"
    except Exception as exc:
        # Do not persist provider bodies or credentials in diagnostic output.
        result.update(status="not_verified", error_type=type(exc).__name__)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path.home() / ".cache/sergio/connectors-public.json",
    )
    args = parser.parse_args()
    entries = directory()
    remotes = [e for e in entries if e["kind"] == "remote"]
    for entry in remotes:
        oauth.validate_endpoint(entry["url"])
    signature = hashlib.sha256(
        b"v2-verified-metadata" + json.dumps(remotes, sort_keys=True).encode()
    ).hexdigest()
    if not args.live:
        print(
            json.dumps(
                {
                    "catalog_entries": len(entries),
                    "remote_urls_valid": len(remotes),
                    "network_tested": False,
                }
            )
        )
        return
    cached = {}
    try:
        cached = json.loads(args.cache.read_text())
    except (OSError, ValueError):
        pass
    if (
        not args.refresh
        and cached.get("signature") == signature
        and 0 <= time.time() - cached.get("created", 0) < 3600
    ):
        cached["cache_hit"] = True
        print(json.dumps(cached, ensure_ascii=False, indent=2))
        return
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check, remotes))
    output = {
        "created": time.time(),
        "signature": signature,
        "cache_hit": False,
        "account_connections_verified": 0,
        "results": results,
    }
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    args.cache.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
