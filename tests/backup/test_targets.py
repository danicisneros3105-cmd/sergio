"""Backup targets: folders, S3 (signed requests against a fake server), SFTP parsing."""

from __future__ import annotations

import datetime as dt
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from openjarvis.backup.targets import (
    FolderTarget,
    S3Target,
    SftpTarget,
    TargetError,
    open_target,
    sigv4_headers,
)


def test_folder_target(tmp_path):
    t = open_target(str(tmp_path / "dest"))
    assert isinstance(t, FolderTarget)
    t.put("a/b.age", b"1")
    t.put("c.age", b"2")
    assert t.list() == ["a/b.age", "c.age"] and t.list("a/") == ["a/b.age"]
    assert t.get("a/b.age") == b"1" and t.exists("c.age")
    t.delete("c.age")
    assert not t.exists("c.age")
    with pytest.raises(TargetError):
        t.get("nope")
    for bad in ("../x", "/abs", "a/../../b", "spa ce"):
        with pytest.raises(TargetError):
            t.put(bad, b"x")


def test_sigv4_matches_the_aws_example():
    headers = sigv4_headers(
        "GET",
        "examplebucket.s3.amazonaws.com",
        "/test.txt",
        {},
        {"Range": "bytes=0-9"},
        b"",
        key_id="AKIAIOSFODNN7EXAMPLE",
        secret="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        now=dt.datetime(2013, 5, 24, tzinfo=dt.timezone.utc),
    )
    assert headers["authorization"].endswith(
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


class FakeS3:
    """Path-style S3 with list-type=2, checking that every request is signed."""

    def __init__(self):
        self.objects = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=KEY/"
        )
        parsed = urlparse(str(request.url))
        parts = parsed.path.lstrip("/").split("/", 1)
        key = parts[1] if len(parts) > 1 else ""
        if request.method == "PUT":
            self.objects[key] = request.content
            return httpx.Response(200)
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        if key:
            if key not in self.objects:
                return httpx.Response(404)
            return httpx.Response(200, content=self.objects[key])
        prefix = parse_qs(parsed.query).get("prefix", [""])[0]
        items = "".join(
            f"<Contents><Key>{k}</Key></Contents>"
            for k in sorted(self.objects)
            if k.startswith(prefix)
        )
        body = (
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"{items}<IsTruncated>false</IsTruncated></ListBucketResult>"
        )
        return httpx.Response(200, content=body.encode())


def test_s3_target_against_a_fake_server():
    fake = FakeS3()
    t = open_target(
        "s3://bucket/sergio?endpoint=https://s3.us-west-002.backblazeb2.com&region=us-west-002",
        key_id="KEY",
        secret="SECRET",
        transport=httpx.MockTransport(fake),
    )
    assert isinstance(t, S3Target) and t.region == "us-west-002"
    t.put("sync/o/abc", b"data")
    assert fake.objects == {"sergio/sync/o/abc": b"data"}
    assert t.get("sync/o/abc") == b"data"
    assert t.list("sync/") == ["sync/o/abc"]
    t.delete("sync/o/abc")
    with pytest.raises(TargetError):
        t.get("sync/o/abc")


def test_s3_needs_keys(monkeypatch):
    for var in (
        "SERGIO_S3_KEY_ID",
        "SERGIO_S3_SECRET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(TargetError, match="claves S3"):
        open_target("s3://bucket/x")


def test_url_parsing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/sftp")
    t = open_target("sftp://dani@nas.local:2222/backups/sergio")
    assert isinstance(t, SftpTarget) and t.dest == "dani@nas.local" and t.port == 2222
    assert t.path == "/backups/sergio"
    assert isinstance(open_target("file:///tmp/x"), FolderTarget)
    with pytest.raises(TargetError):
        open_target("ftp://old")
    with pytest.raises(TargetError):
        open_target("")
