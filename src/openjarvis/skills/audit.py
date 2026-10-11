"""Bounded, offline skill triage inspired by SkillScanner's static mode.

Original implementation: no Swarms runtime, model call, URL fetch or execution.
Findings contain rule IDs and line numbers only, never matched secrets.
Heuristics are a pre-installation check, not a proof of safety or a sandbox.
"""

from __future__ import annotations

__all__ = ["SkillAudit", "audit_text", "audit_resources", "read_skill_text"]

import base64
import binascii
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

MAX_TEXT_BYTES = 262_144
MAX_FILES = 500
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".py",
    ".sh",
    ".ps1",
    ".js",
    ".ts",
}
RULES = (
    (
        "instruction_override",
        re.compile(
            r"\b(?:ignore|disregard|override|ignora|ignorar|omite|omitir)\b[^\n.]{0,60}"
            r"\b(?:instructions?|rules|instrucciones|reglas)\b",
            re.I,
        ),
    ),
    (
        "role_spoofing",
        re.compile(r"<\|(?:im_start|system|assistant)\|>|<system>|\[INST\]", re.I),
    ),
    (
        "hidden_controls",
        re.compile("[\u202a-\u202e\u2066-\u2069\U000e0000-\U000e007f]"),
    ),
    (
        "embedded_secret",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
            r"\bgh[pousr]_[A-Za-z0-9]{36,}|\bsk-(?:ant-)?[A-Za-z0-9_-]{24,}"
        ),
    ),
)
BASE64 = re.compile(r"(?<![\w+/])[A-Za-z0-9+/]{40,}={0,2}(?![\w+/=])")


@dataclass(frozen=True)
class SkillAudit:
    sha256: str
    findings: tuple[str, ...]


def audit_text(text: str) -> SkillAudit:
    raw = text.encode("utf-8")
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("Skill text exceeds the 256 KiB audit limit")
    findings: list[str] = []

    def scan(value: str, depth: int = 0, original_line: int | None = None) -> None:
        for rule, pattern in RULES:
            match = pattern.search(value)
            if match:
                line = original_line or value.count("\n", 0, match.start()) + 1
                finding = f"{rule}: line {line}"
                if finding not in findings:
                    findings.append(finding)
        if depth >= 2:
            return
        # Decoding only: bounded input and depth, no eval or remote requests.
        for match in BASE64.finditer(value):
            try:
                decoded = base64.b64decode(match.group(), validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                continue
            line = original_line or value.count("\n", 0, match.start()) + 1
            scan(decoded, depth + 1, line)

    scan(text)
    return SkillAudit(hashlib.sha256(raw).hexdigest(), tuple(findings))


def read_skill_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Refusing to read a symlinked or special skill file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("Skill text exceeds the 256 KiB audit limit")
    return raw.decode("utf-8")


def audit_resources(root: Path, subdirs: list[str]) -> tuple[str, ...]:
    """Audit exactly the resources selected for import; never follow links."""
    findings: list[str] = []
    count = total = directories = 0
    for name in subdirs:
        directory = root / name
        if directory.is_symlink():
            raise ValueError("Refusing symlinked skill resources")
        if not directory.exists():
            continue
        for parent, dirs, files in os.walk(directory, followlinks=False):
            directories += 1
            if directories > MAX_FILES:
                raise ValueError("Skill directories exceed the audit budget")
            if any((Path(parent) / d).is_symlink() for d in dirs):
                raise ValueError("Refusing symlinked skill resources")
            for filename in files:
                path = Path(parent) / filename
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Refusing symlinked or special skill resources")
                count += 1
                total += path.stat().st_size
                if count > MAX_FILES or total > MAX_PACKAGE_BYTES:
                    raise ValueError("Skill resources exceed the audit budget")
                if path.suffix.lower() in TEXT_SUFFIXES:
                    report = audit_text(read_skill_text(path))
                    findings.extend(
                        f"{path.relative_to(root)}: {f}" for f in report.findings
                    )
                    if len(findings) >= 20:
                        return tuple(findings[:20])
    return tuple(findings)
