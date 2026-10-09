"""The pure-Python twins behave like the Rust extension (parity when both exist)."""

from __future__ import annotations

import json

import pytest

from openjarvis import _native_fallback as py
from openjarvis._rust_bridge import RUST_AVAILABLE, get_native

needs_rust = pytest.mark.skipif(
    not RUST_AVAILABLE, reason="parity needs the native extension"
)

SAMPLES = [
    "plain text, nothing secret",
    "key sk-abcdefghijklmnopqrstuvwxyz123 and AKIAABCDEFGHIJKLMNOP",
    'password = "hunter22" api_key: "0123456789abcdef"',
    "-----BEGIN RSA PRIVATE KEY----- xoxb-1234567890-abc",
    "mail me at ana.perez@example.org or call (555) 123-4567, SSN 123-45-6789",
    "card 4111 1111 1111 1111, amex 3782 822463 10005, server 10.0.0.12",
    "postgres://user:pass@db.internal:5432/app",
]


def _rust():
    from openjarvis._rust_bridge import get_rust_module

    return get_rust_module()


# -- capability policy ---------------------------------------------------------


@pytest.mark.parametrize(
    "pattern,text,expected",
    [
        ("*", "anything", True),
        ("file:*", "file:read", True),
        ("file:*", "network:fetch", False),
        ("*:read", "file:read", True),
        ("f*e:r*d", "file:read", True),
        ("file:read", "file:readx", False),
        ("/home/*", "/home/ana/notes.txt", True),
        ("*.txt", "notes.md", False),
    ],
)
def test_glob_match(pattern, text, expected):
    assert py.glob_match(pattern, text) is expected


def test_capability_policy_rules():
    policy = py.CapabilityPolicy(default_deny=True)
    assert policy.check("nobody", "file:read", "") is False  # no policy -> default
    policy.grant("a", "file:*", "/home/*")
    policy.deny("a", "file:write")
    assert policy.check("a", "file:read", "/home/ana/x") is True
    assert policy.check("a", "file:read", "/etc/passwd") is False
    assert policy.check("a", "file:read", "") is True  # no resource -> grant applies
    assert policy.check("a", "file:write", "/home/ana/x") is False  # deny wins
    assert policy.list_agents() == ["a"]
    assert py.CapabilityPolicy(default_deny=False).check("x", "anything", "") is True


@needs_rust
def test_capability_policy_parity():
    cases = [
        ("a", "file:read", "/home/ana/x"),
        ("a", "file:read", "/etc"),
        ("a", "file:write", ""),
        ("a", "network:fetch", ""),
        ("b", "code:execute", ""),
    ]
    for deny in (True, False):
        mine, theirs = (
            py.CapabilityPolicy(default_deny=deny),
            _rust().CapabilityPolicy(default_deny=deny),
        )
        for impl in (mine, theirs):
            impl.grant("a", "file:*", "/home/*")
            impl.deny("a", "file:write")
        for case in cases:
            assert mine.check(*case) == theirs.check(*case), case


# -- scanners ------------------------------------------------------------------


def test_secret_scanner_finds_and_redacts():
    scanner = py.SecretScanner()
    found = json.loads(scanner.scan(SAMPLES[1]))["findings"]
    assert {f["pattern_name"] for f in found} == {"openai_key", "aws_access_key"}
    redacted = scanner.redact(SAMPLES[1])
    assert "sk-abc" not in redacted and "[REDACTED:aws_access_key]" in redacted


@needs_rust
@pytest.mark.parametrize("name", ["SecretScanner", "PIIScanner"])
def test_scanner_parity(name):
    mine, theirs = getattr(py, name)(), getattr(_rust(), name)()
    for text in SAMPLES:
        a = [
            (f["pattern_name"], f["matched_text"], f["threat_level"])
            for f in json.loads(mine.scan(text))["findings"]
        ]
        b = [
            (f["pattern_name"], f["matched_text"], f["threat_level"])
            for f in json.loads(theirs.scan(text))["findings"]
        ]
        assert a == b, text
        assert mine.redact(text) == theirs.redact(text), text


def test_security_scanner_classes_work_without_rust(monkeypatch):
    import openjarvis._rust_bridge as bridge
    from openjarvis.security.scanner import PIIScanner, SecretScanner

    def _missing():
        raise ImportError("No module named 'openjarvis_rust'")

    monkeypatch.setattr(bridge, "get_rust_module", _missing)
    assert not SecretScanner().scan(SAMPLES[1]).clean
    assert "[REDACTED:email]" in PIIScanner().redact(SAMPLES[4])


# -- rate limiter ----------------------------------------------------------------


def test_rate_limiter_burst_then_wait_then_reset():
    limiter = py.RateLimiter(requests_per_minute=60, burst_size=2)
    assert limiter.check("k") == (True, 0.0)
    assert limiter.check("k") == (True, 0.0)
    allowed, wait = limiter.check("k")
    assert allowed is False and 0 < wait <= 1.0
    assert limiter.check("other")[0] is True  # buckets are per key
    limiter.reset("k")
    assert limiter.check("k")[0] is True
    limiter.reset()
    assert limiter.check("other")[0] is True


# -- loop guard ------------------------------------------------------------------


def test_loop_guard_parity_sequence():
    calls = [("a", "1"), ("b", "1"), ("a", "2"), ("b", "2"), ("a", "1"), ("c", "x")]
    mine = py.LoopGuard(50, 4, 100)
    got = [mine.check(*c) for c in calls]
    assert got[0] is None and got[1] is None and got[2] is None
    assert got[3] is not None and "Ping-pong" in got[3]
    assert "identical" in got[4]
    if RUST_AVAILABLE:
        theirs = _rust().LoopGuard(max_identical=50, max_ping_pong=4, poll_budget=100)
        assert [theirs.check(*c) for c in calls] == got


def test_loop_guard_poll_budget():
    guard = py.LoopGuard(poll_budget=2)
    assert guard.check("t", "1") is None
    assert guard.check("u", "2") is None
    assert "budget" in guard.check("v", "3")


# -- memories --------------------------------------------------------------------

DOCS = [
    ("The user's favourite drink is green tea with honey", "notes"),
    ("Meeting with Ana about the budget on Friday", "calendar"),
    ("Tea kettle is broken; buy a new kettle", "notes"),
]


def _fill(mem):
    for content, source in DOCS:
        mem.store(content, source, json.dumps({"from": source}))


@pytest.mark.parametrize("cls", [py.SQLiteMemory, py.BM25Memory])
def test_memory_store_retrieve_delete(cls, tmp_path):
    mem = cls(str(tmp_path / "m.db")) if cls is py.SQLiteMemory else cls()
    _fill(mem)
    assert mem.count() == 3
    hits = json.loads(mem.retrieve("kettle", 5))
    assert hits and "kettle" in hits[0]["content"].lower()
    assert hits[0]["metadata"] == {"from": "notes"} and hits[0]["score"] > 0
    doc_id = mem.store("temporary", "x")
    assert mem.delete(doc_id) is True and mem.delete(doc_id) is False
    mem.clear()
    assert mem.count() == 0


def test_sqlite_query_syntax_never_breaks(tmp_path):
    mem = py.SQLiteMemory(str(tmp_path / "m.db"))
    _fill(mem)
    for query in ("user's drink", "tea OR", "NOT budget", "AND", '"quoted"', "***", ""):
        json.loads(mem.retrieve(query, 3))  # no sqlite3.OperationalError
    assert json.loads(mem.retrieve("user's drink", 3))[0]["source"] == "notes"


def test_sqlite_replace_source_and_persistence(tmp_path):
    path = str(tmp_path / "m.db")
    mem = py.SQLiteMemory(path)
    _fill(mem)
    ids = mem.replace_source("notes", [("fresh note about coffee", None)])
    assert len(ids) == 1 and mem.count() == 2
    again = py.SQLiteMemory(path)
    assert again.count() == 2
    assert (
        json.loads(again.retrieve("coffee", 1))[0]["content"]
        == "fresh note about coffee"
    )


@needs_rust
def test_sqlite_database_is_shared_with_rust(tmp_path):
    path = str(tmp_path / "shared.db")
    py.SQLiteMemory(path).store("written by python about volcanoes", "py", None)
    rust = _rust().SQLiteMemory(path)
    rust.store("written by rust about glaciers", "rs", None)
    assert rust.count() == 2
    assert json.loads(rust.retrieve("volcanoes", 1))[0]["source"] == "py"
    assert (
        json.loads(py.SQLiteMemory(path).retrieve("glaciers", 1))[0]["source"] == "rs"
    )


@needs_rust
def test_bm25_parity():
    mine, theirs = py.BM25Memory(), _rust().BM25Memory()
    for impl in (mine, theirs):
        _fill(impl)
    for query in ("tea", "kettle broken", "budget Ana", "nothing-matches"):
        a = [
            (h["content"], round(h["score"], 6))
            for h in json.loads(mine.retrieve(query, 5))
        ]
        b = [
            (h["content"], round(h["score"], 6))
            for h in json.loads(theirs.retrieve(query, 5))
        ]
        assert a == b, query


def test_get_native_falls_back(monkeypatch):
    import openjarvis._rust_bridge as bridge

    def _missing():
        raise ImportError("No module named 'openjarvis_rust'")

    monkeypatch.setattr(bridge, "get_rust_module", _missing)
    assert get_native("SQLiteMemory") is py.SQLiteMemory
    assert get_native("CapabilityPolicy") is py.CapabilityPolicy
