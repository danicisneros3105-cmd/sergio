"""The companion's recent errors, read back from its log for `sergio probar`."""

from sergio_escritorio.diagnose import recent_errors


def test_recent_errors_with_their_reason(tmp_path):
    log = tmp_path / "sergio.log"
    log.write_text(
        "2026-10-04 10:00:00,001 INFO instant wake word on\n"
        "2026-10-04 10:00:05,002 WARNING live call unavailable: 1011 quota\n"
        "2026-10-04 10:00:06,003 ERROR voice turn failed\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in <module>\n'
        "httpx.ConnectError: [Errno 111] Connection refused\n"
        "2026-10-04 10:00:07,004 INFO all fine\n",
        encoding="utf-8",
    )
    assert recent_errors(log) == [
        "10:00:05 live call unavailable: 1011 quota",
        "10:00:06 voice turn failed — httpx.ConnectError: [Errno 111] Connection refused",
    ]
    assert recent_errors(tmp_path / "missing.log") == []


def test_selftest_route_runs_the_app_test(control_server):
    import httpx

    controller, url = control_server
    auth = {"Authorization": "Bearer secreto"}
    assert httpx.post(f"{url}/selftest", headers=auth, json={"kind": "call"}).status_code == 404
    controller.selftest = lambda kind: {"ok": True, "kind": kind}
    resp = httpx.post(f"{url}/selftest", headers=auth, json={"kind": "turn"})
    assert resp.json() == {"ok": True, "kind": "turn"}
