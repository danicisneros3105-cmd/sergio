"""Polyglot Coder: write, run and translate code in many languages.

``RUNTIMES`` knows how to run Python, JavaScript (Node), TypeScript (via
Node's type stripping or tsx), Bash, Ruby, Go, Rust, C, C++, Java, PHP and
Lua — whichever are installed. ``run`` executes a snippet in a temporary
folder with a timeout. ``translate`` converts code between languages and
*verifies* it: both versions run on the same stdin and the translation is
only reported as correct when their output matches.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm
from openjarvis.tools.code_generator import code_block


@dataclass(frozen=True)
class Runtime:
    language: str
    file: str
    needs: tuple[str, ...]
    steps: tuple[tuple[str, ...], ...]  # commands; {file} {dir} {exe} placeholders
    fence: str


RUNTIMES: dict[str, Runtime] = {r.language: r for r in (
    Runtime("python", "main.py", ("python3",), (("python3", "-I", "{file}"),), "python"),
    Runtime("javascript", "main.js", ("node",), (("node", "{file}"),), "javascript"),
    Runtime("typescript", "main.ts", ("node",), (("node", "--experimental-strip-types", "--no-warnings", "{file}"),),
            "typescript"),
    Runtime("bash", "main.sh", ("bash",), (("bash", "{file}"),), "bash"),
    Runtime("ruby", "main.rb", ("ruby",), (("ruby", "{file}"),), "ruby"),
    Runtime("go", "main.go", ("go",), (("go", "run", "{file}"),), "go"),
    Runtime("rust", "main.rs", ("rustc",), (("rustc", "-O", "-o", "{exe}", "{file}"), ("{exe}",)), "rust"),
    Runtime("c", "main.c", ("cc",), (("cc", "-O2", "-o", "{exe}", "{file}", "-lm"), ("{exe}",)), "c"),
    Runtime("cpp", "main.cpp", ("c++",), (("c++", "-O2", "-std=c++17", "-o", "{exe}", "{file}"), ("{exe}",)), "cpp"),
    Runtime("java", "Main.java", ("java",), (("java", "{file}"),), "java"),
    Runtime("php", "main.php", ("php",), (("php", "{file}"),), "php"),
    Runtime("lua", "main.lua", ("lua",), (("lua", "{file}"),), "lua"),
)}
ALIASES = {"py": "python", "js": "javascript", "node": "javascript", "ts": "typescript", "sh": "bash",
           "shell": "bash", "rb": "ruby", "golang": "go", "rs": "rust", "c++": "cpp", "cxx": "cpp"}

TRANSLATE_PROMPT = """Translate this {src} program to idiomatic {dst}. It must read the
same input (stdin) and print exactly the same output (stdout), byte for byte.
Use only the {dst} standard library.{main_hint} Output only one code block.

```{src}
{code}
```"""

FIX_PROMPT = """Your {dst} translation does not behave like the original.

ORIGINAL ({src}):
```{src}
{code}
```

TRANSLATION ({dst}):
```{dst}
{translated}
```

With input {stdin!r} the original printed:
{expected}
The translation printed:
{got}

Fix the translation. Output only one code block."""


def canonical(language: str) -> str:
    lang = language.strip().lower()
    return ALIASES.get(lang, lang)


def available() -> list[str]:
    return [name for name, rt in RUNTIMES.items() if all(shutil.which(n) for n in rt.needs)]


def detect(code: str) -> str:
    """A best guess at the language of *code*."""
    checks = [
        ("rust", r"\bfn main\s*\(|println!\(|\blet mut\b"),
        ("go", r"^package main|\bfunc main\s*\(|fmt\.Print"),
        ("java", r"public static void main|System\.out\.print"),
        ("cpp", r"#include\s*<(iostream|vector|string)>|std::"),
        ("c", r"#include\s*<stdio\.h>|printf\s*\("),
        ("typescript", r":\s*(number|string|boolean)\b|\binterface \w+\s*\{"),
        ("javascript", r"console\.log|\bconst \w+\s*=|=>|require\("),
        ("php", r"<\?php"),
        ("ruby", r"\bputs\b|\bend\s*$|\.each do"),
        ("lua", r"\blocal \w+\s*=|\bprint\(.*\)\s*$.*\bend\b"),
        ("bash", r"^#!/bin/(ba)?sh|\becho\b|\$\{?\w+\}?"),
        ("python", r"\bdef \w+\(|\bprint\(|\bimport \w+|:\s*$"),
    ]
    for lang, pattern in checks:
        if re.search(pattern, code, re.M):
            return lang
    return "python"


@dataclass
class RunOutput:
    ok: bool
    stdout: str
    stderr: str
    language: str
    code: int


def run(code: str, language: str, stdin: str = "", timeout: float = 30.0) -> RunOutput:
    lang = canonical(language)
    rt = RUNTIMES.get(lang)
    if rt is None:
        return RunOutput(False, "", f"unknown language {language}", lang, -1)
    missing = [n for n in rt.needs if not shutil.which(n)]
    if missing:
        return RunOutput(False, "", f"{lang} is not installed (needs {', '.join(missing)})", lang, -1)
    with tempfile.TemporaryDirectory() as tmp:
        file = Path(tmp) / rt.file
        file.write_text(code, "utf-8")
        exe = str(Path(tmp) / "prog")
        proc = None
        for step in rt.steps:
            cmd = [part.format(file=str(file), dir=tmp, exe=exe) for part in step]
            try:
                proc = subprocess.run(cmd, input=stdin if step is rt.steps[-1] else None, capture_output=True,
                                      text=True, timeout=timeout, cwd=tmp)
            except subprocess.TimeoutExpired:
                return RunOutput(False, "", f"timed out after {timeout:.0f} s", lang, -9)
            if proc.returncode != 0:
                break
    assert proc is not None
    return RunOutput(proc.returncode == 0, proc.stdout, proc.stderr[-3000:], lang, proc.returncode)


@dataclass
class Translation:
    code: str
    source_language: str
    target_language: str
    verified: bool
    rounds: int
    note: str = ""


def translate(
    code: str,
    target: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    source: Optional[str] = None,
    stdin_cases: tuple[str, ...] = ("",),
    max_rounds: int = 3,
) -> Translation:
    """Translate *code* to *target*; verified by running both on *stdin_cases*."""
    model = as_llm(llm)
    src = canonical(source or detect(code))
    dst = canonical(target)
    hint = " The class must be named Main." if dst == "java" else (" Use package main." if dst == "go" else "")
    translated = code_block(model(TRANSLATE_PROMPT.format(src=src, dst=dst, code=code, main_hint=hint),
                                  temperature=0.2), dst)
    can_check = src in available() and dst in available()
    if not can_check:
        return Translation(translated, src, dst, False, 1, "not verified: a runtime is missing")
    expected = {s: run(code, src, s) for s in stdin_cases}
    for rnd in range(1, max_rounds + 1):
        bad = None
        for s in stdin_cases:
            got = run(translated, dst, s)
            if not got.ok or got.stdout != expected[s].stdout:
                bad = (s, got)
                break
        if bad is None:
            return Translation(translated, src, dst, True, rnd, "same output on every test input")
        if rnd == max_rounds:
            break
        s, got = bad
        translated = code_block(model(FIX_PROMPT.format(src=src, dst=dst, code=code, translated=translated, stdin=s,
                                                        expected=expected[s].stdout[:2000],
                                                        got=(got.stdout or got.stderr)[:2000]), temperature=0.2), dst)
    return Translation(translated, src, dst, False, max_rounds, "outputs still differ")


__all__ = ["RUNTIMES", "RunOutput", "Translation", "available", "canonical", "detect", "run", "translate"]
