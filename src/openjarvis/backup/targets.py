"""Where encrypted backups and sync data are kept.

A target is a URL:

* ``/ruta/a/carpeta`` or ``file:///ruta`` — a folder (an external disk, or a
  Dropbox / Google Drive / OneDrive folder, which then syncs it for you);
* ``s3://bucket/prefijo?endpoint=https://…&region=…`` — Amazon S3 or any S3
  compatible service: Backblaze B2, Cloudflare R2, Wasabi, MinIO. Keys come
  from ``SERGIO_S3_KEY_ID`` / ``SERGIO_S3_SECRET`` (or the usual
  ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``) in ``sergio.env``;
* ``sftp://usuario@servidor:22/ruta`` — any SSH server, using your SSH keys
  (the ``sftp`` program, in batch mode: no password prompts).

Everything a target stores is already encrypted; it only ever sees opaque
names and bytes.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._/-]{1,512}$")


class TargetError(RuntimeError):
    """The target could not be reached or refused the operation."""


def _check(name: str) -> str:
    if (
        not _SAFE_NAME.match(name)
        or ".." in PurePosixPath(name).parts
        or name.startswith("/")
    ):
        raise TargetError(f"nombre de objeto inválido: {name!r}")
    return name


class Target:
    url = ""

    def put(self, name: str, data: bytes) -> None:
        raise NotImplementedError

    def get(self, name: str) -> bytes:
        raise NotImplementedError

    def list(self, prefix: str = "") -> List[str]:
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError

    def exists(self, name: str) -> bool:
        return name in self.list(name.rsplit("/", 1)[0] + "/" if "/" in name else "")

    def describe(self) -> str:
        return self.url


class FolderTarget(Target):
    def __init__(self, path: Path) -> None:
        self.root = path.expanduser()
        self.url = str(self.root)

    def _path(self, name: str) -> Path:
        return self.root / _check(name)

    def put(self, name: str, data: bytes) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".partial")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, name: str) -> bytes:
        try:
            return self._path(name).read_bytes()
        except FileNotFoundError:
            raise TargetError(f"no existe {name}") from None

    def list(self, prefix: str = "") -> List[str]:
        if not self.root.is_dir():
            return []
        out = []
        for path in self.root.rglob("*"):
            if path.is_file() and not path.name.endswith(".partial"):
                rel = path.relative_to(self.root).as_posix()
                if rel.startswith(prefix):
                    out.append(rel)
        return sorted(out)

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()


# -- S3 (and Backblaze B2, R2, Wasabi, MinIO) ------------------------------------


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def sigv4_headers(
    method: str,
    host: str,
    path: str,
    query: Dict[str, str],
    headers: Dict[str, str],
    payload: bytes,
    *,
    key_id: str,
    secret: str,
    region: str,
    now: Optional[_dt.datetime] = None,
    service: str = "s3",
) -> Dict[str, str]:
    """Headers (with Authorization) for an AWS Signature Version 4 request."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    payload_hash = hashlib.sha256(payload).hexdigest()
    all_headers = {k.lower(): v.strip() for k, v in headers.items()}
    all_headers.update(
        {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    )
    signed = ";".join(sorted(all_headers))
    canonical_headers = "".join(f"{k}:{all_headers[k]}\n" for k in sorted(all_headers))
    canonical_query = "&".join(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}"
        for k, v in sorted(query.items())
    )
    canonical_uri = quote(path or "/", safe="/-_.~")
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed,
            payload_hash,
        ]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    key = _hmac(("AWS4" + secret).encode(), day)
    key = _hmac(_hmac(_hmac(key, region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    all_headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, "
        f"SignedHeaders={signed}, Signature={signature}"
    )
    return all_headers


class S3Target(Target):
    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        *,
        endpoint: str = "",
        region: str = "",
        key_id: str = "",
        secret: str = "",
        transport: object = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.region = region or os.environ.get("SERGIO_S3_REGION") or "us-east-1"
        self.endpoint = (
            endpoint
            or os.environ.get("SERGIO_S3_ENDPOINT")
            or f"https://s3.{self.region}.amazonaws.com"
        ).rstrip("/")
        self.key_id = (
            key_id
            or os.environ.get("SERGIO_S3_KEY_ID")
            or os.environ.get("AWS_ACCESS_KEY_ID", "")
        )
        self.secret = (
            secret
            or os.environ.get("SERGIO_S3_SECRET")
            or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        )
        self.transport = transport
        self.url = f"s3://{bucket}/{self.prefix}"
        if not self.key_id or not self.secret:
            raise TargetError(
                "faltan las claves S3: ponga SERGIO_S3_KEY_ID y SERGIO_S3_SECRET en sergio.env"
            )

    def _key(self, name: str) -> str:
        name = _check(name)
        return f"{self.prefix}/{name}" if self.prefix else name

    def _request(
        self,
        method: str,
        key: str = "",
        query: Optional[Dict[str, str]] = None,
        body: bytes = b"",
    ) -> Tuple[int, bytes]:
        import httpx

        parsed = urlparse(self.endpoint)
        path = f"/{self.bucket}" + (f"/{key}" if key else "")
        query = query or {}
        headers = sigv4_headers(
            method,
            parsed.netloc,
            path,
            query,
            {},
            body,
            key_id=self.key_id,
            secret=self.secret,
            region=self.region,
        )
        headers.pop("host", None)
        url = f"{parsed.scheme}://{parsed.netloc}{quote(path, safe='/-_.~')}"
        kwargs = {"transport": self.transport} if self.transport is not None else {}
        with httpx.Client(timeout=120, **kwargs) as client:
            resp = client.request(
                method, url, params=query or None, headers=headers, content=body
            )
        return resp.status_code, resp.content

    def put(self, name: str, data: bytes) -> None:
        status, body = self._request("PUT", self._key(name), body=data)
        if status >= 300:
            raise TargetError(f"S3 rechazó la subida ({status}): {body[:200]!r}")

    def get(self, name: str) -> bytes:
        status, body = self._request("GET", self._key(name))
        if status == 404:
            raise TargetError(f"no existe {name}")
        if status >= 300:
            raise TargetError(f"S3 rechazó la descarga ({status})")
        return body

    def list(self, prefix: str = "") -> List[str]:
        full = (
            self._key(prefix) if prefix else (self.prefix + "/" if self.prefix else "")
        )
        names: List[str] = []
        token = ""
        while True:
            query = {"list-type": "2", "prefix": full}
            if token:
                query["continuation-token"] = token
            status, body = self._request("GET", query=query)
            if status >= 300:
                raise TargetError(f"S3 no deja listar ({status})")
            root = ET.fromstring(body)
            ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
            for item in root.iter(f"{ns}Contents"):
                key = item.findtext(f"{ns}Key") or ""
                if self.prefix:
                    key = key[len(self.prefix) + 1 :]
                names.append(key)
            if (root.findtext(f"{ns}IsTruncated") or "false") != "true":
                break
            token = root.findtext(f"{ns}NextContinuationToken") or ""
        return sorted(names)

    def delete(self, name: str) -> None:
        status, _ = self._request("DELETE", self._key(name))
        if status >= 300 and status != 404:
            raise TargetError(f"S3 no dejó borrar ({status})")


# -- SFTP ------------------------------------------------------------------------


class SftpTarget(Target):
    def __init__(self, user: str, host: str, port: int, path: str) -> None:
        if not shutil.which("sftp"):
            raise TargetError("falta el programa sftp (OpenSSH)")
        self.dest = f"{user}@{host}" if user else host
        self.port = port or 22
        self.path = path.rstrip("/") or "."
        self.url = f"sftp://{self.dest}:{self.port}{self.path}"

    def _batch(self, commands: List[str]) -> str:
        script = "\n".join(commands) + "\n"
        done = subprocess.run(
            [
                "sftp",
                "-q",
                "-b",
                "-",
                "-P",
                str(self.port),
                "-o",
                "BatchMode=yes",
                self.dest,
            ],
            input=script,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if done.returncode != 0:
            raise TargetError(
                f"sftp falló: {(done.stderr or done.stdout).strip()[:300]}"
            )
        return done.stdout

    def _remote(self, name: str) -> str:
        return f"{self.path}/{_check(name)}"

    def put(self, name: str, data: bytes) -> None:
        remote = self._remote(name)
        parts = PurePosixPath(remote).parent.parts
        mkdirs = [f"-mkdir {PurePosixPath(*parts[: i + 1])}" for i in range(len(parts))]
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(data)
            local = fh.name
        try:
            self._batch(
                mkdirs
                + [
                    f'put "{local}" "{remote}.partial"',
                    f'rename "{remote}.partial" "{remote}"',
                ]
            )
        finally:
            os.unlink(local)

    def get(self, name: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "obj"
            self._batch([f'get "{self._remote(name)}" "{local}"'])
            return local.read_bytes()

    def list(self, prefix: str = "") -> List[str]:
        folder = PurePosixPath(self._remote(prefix + "x")).parent
        try:
            out = self._batch([f'ls -1 "{folder}"'])
        except TargetError:
            return []
        rel_dir = PurePosixPath(prefix + "x").parent.as_posix()
        names = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("sftp>"):
                continue
            base = line.rsplit("/", 1)[-1]
            rel = base if rel_dir in ("", ".") else f"{rel_dir}/{base}"
            if rel.startswith(prefix) and not rel.endswith(".partial"):
                names.append(rel)
        return sorted(names)

    def delete(self, name: str) -> None:
        self._batch([f'-rm "{self._remote(name)}"'])


def open_target(url: str, **kw: object) -> Target:
    """The target for a URL (see the module docstring)."""
    url = (url or "").strip()
    if not url:
        raise TargetError("no hay destino configurado")
    if url.startswith("s3://"):
        parsed = urlparse(url)
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        return S3Target(
            parsed.netloc,
            parsed.path,
            endpoint=params.get("endpoint", ""),
            region=params.get("region", ""),
            **kw,  # type: ignore[arg-type]
        )
    if url.startswith("sftp://"):
        parsed = urlparse(url)
        return SftpTarget(
            parsed.username or "", parsed.hostname or "", parsed.port or 22, parsed.path
        )
    if url.startswith("file://"):
        return FolderTarget(Path(urlparse(url).path))
    if "://" in url:
        raise TargetError("destino no soportado: use una carpeta, s3:// o sftp://")
    return FolderTarget(Path(url))


__all__ = [
    "FolderTarget",
    "S3Target",
    "SftpTarget",
    "Target",
    "TargetError",
    "open_target",
    "sigv4_headers",
]
