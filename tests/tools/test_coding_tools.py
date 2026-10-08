"""The eight coding tools: real code runs, scripted models (no network)."""

from __future__ import annotations

import json
import shutil
import sys
import textwrap

import pytest

from openjarvis.intelligence._llm import LLM
from openjarvis.intelligence.long_context import answer_long, bm25_rank, chunk_text
from openjarvis.tools.code_generator import code_block, run_pytest, tdd
from openjarvis.tools.code_review import review, static_review
from openjarvis.tools.debugger import analyse, culprit, debug_run, parse_traceback
from openjarvis.tools.doc_generator import (
    add_docstrings,
    api_markdown,
    docstring_drift,
    markdown_drift,
)
from openjarvis.tools.optimizer import (
    benchmark,
    optimize_function,
    profile_call,
    profile_script,
)
from openjarvis.tools.polyglot import available, detect, run, translate
from openjarvis.tools.refactor import (
    Change,
    apply_atomically,
    llm_refactor,
    rename_symbol,
)


def model(rules):
    def fn(prompt):
        for key, reply in rules:
            if key in prompt:
                return reply.pop(0) if isinstance(reply, list) and len(reply) > 1 else (
                    reply[0] if isinstance(reply, list) else reply(prompt) if callable(reply) else reply)
        return ""

    return LLM(fn)


# -- long context ----------------------------------------------------------------
def test_long_text_is_chunked_ranked_and_answered_with_citations():
    filler = "\n\n".join(f"Capítulo {i}. El viajero camina por el bosque y no pasa nada." for i in range(400))
    text = filler + "\n\nCapítulo final. La dragona Ixchel fue vencida por la herrera Marta.\n\n" + filler
    chunks = chunk_text(text, max_tokens=400)
    assert len(chunks) > 20 and chunks[0].start_line == 1
    best = bm25_rank("¿Quién venció a la dragona Ixchel?", chunks)[0][1]
    assert "Ixchel" in best.text
    llm = model([("From this excerpt", lambda p: "NOTHING" if "Ixchel" not in p else "[c] Marta venció a Ixchel."),
                 ("Answer using only", lambda p: "La herrera Marta [c..]." if "Marta" in p else "no sé")])
    r = answer_long("¿Quién venció a la dragona Ixchel?", text, llm, chunk_tokens=400, window_tokens=1000,
                    max_chunks=3)
    assert "Marta" in r.answer and len(r.read) <= 3 and r.chunks == len(chunks)


# -- TDD -------------------------------------------------------------------------
def test_tdd_writes_tests_then_fixes_code_until_green():
    tests = "from solution import *\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n"
    llm = model([
        ("Write pytest tests", f"```python\n{tests}```"),
        ("satisfies the specification", "```python\ndef add(a, b):\n    return a - b\n```"),
        ("fails its tests", lambda p: "```python\ndef add(a, b):\n    return a + b\n```" if "assert" in p else ""),
    ])
    r = tdd("add two numbers", llm)
    assert r.ok and r.rounds == 2 and "a + b" in r.code
    assert r.history[0]["failed"] >= 1
    assert code_block("text\n```py\nx = 1\n```") == "x = 1\n"
    stuck = run_pytest("while True: pass", "from solution import *\ndef test_x():\n    pass\n", timeout=3)
    assert not stuck.ok and "timed out" in stuck.output


# -- refactor --------------------------------------------------------------------
def test_rename_across_files_is_atomic(tmp_path):
    (tmp_path / "a.py").write_text("def count(x):\n    return x  # count\n")
    (tmp_path / "b.py").write_text("from a import count\naccount = count(1)\nprint('count')\n")
    r = rename_symbol(tmp_path, "count", "total")
    assert r.ok and r.renames == {str(tmp_path / "a.py"): 1, str(tmp_path / "b.py"): 2}
    assert (tmp_path / "b.py").read_text() == "from a import total\naccount = total(1)\nprint('count')\n"
    # a failing test command rolls every file back
    r2 = rename_symbol(tmp_path, "total", "suma", test_cmd=f"{sys.executable} -c 'raise SystemExit(1)'")
    assert not r2.ok and "rolled back" in r2.reason and "total" in (tmp_path / "a.py").read_text()


def test_broken_code_is_never_left_behind(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    r = apply_atomically([Change(f, "x = (\n"), Change(tmp_path / "new.py", "y = 2\n")])
    assert not r.ok and f.read_text() == "x = 1\n" and not (tmp_path / "new.py").exists()
    llm = model([("Refactor these files", json.dumps({"files": [{"path": str(f), "content": "X = 1\n"},
                                                                 {"path": "/etc/passwd", "content": "no"}],
                                                       "summary": "constant"}))])
    r2 = llm_refactor("make it a constant", [f], llm)
    assert r2.ok and r2.changed == [str(f)] and f.read_text() == "X = 1\n"


# -- debugger --------------------------------------------------------------------
PY_TRACE = """Traceback (most recent call last):
  File "/app/main.py", line 10, in <module>
    run()
  File "/app/main.py", line 7, in run
    print(user["name"].upper())
  File "/usr/lib/python3.11/site-packages/lib/x.py", line 3, in helper
    pass
AttributeError: 'NoneType' object has no attribute 'upper'
"""


def test_stack_analysis_picks_the_users_frame_and_explains():
    t = parse_traceback(PY_TRACE)
    assert t.language == "python" and t.exc_type == "AttributeError" and len(t.frames) == 3
    assert culprit(t).line == 7 and culprit(t).func == "run"
    js = parse_traceback("TypeError: Cannot read properties of undefined (reading 'x')\n"
                         "    at render (/app/ui.js:12:5)\n    at main (/app/index.js:3:1)\n")
    assert js.language == "javascript" and culprit(js).file == "/app/ui.js"
    d = analyse(PY_TRACE)
    assert "None" in d.hint
    llm = model([("You are debugging", json.dumps({"root_cause": "user['name'] is None", "fix": "check it",
                                                   "patch": "", "confidence": 80}))])
    assert analyse(PY_TRACE, llm).root_cause == "user['name'] is None"


def test_debug_run_reads_the_real_crash(tmp_path):
    (tmp_path / "boom.py").write_text("def f(d):\n    return d['missing']\n\nf({})\n")
    d = debug_run(f"{sys.executable} boom.py", None, cwd=str(tmp_path))
    assert d.trace.exc_type == "KeyError" and d.culprit.line == 2 and "key" in d.hint.lower()
    assert debug_run(f"{sys.executable} -c 'print(1)'", None) is None


# -- review ----------------------------------------------------------------------
def test_static_review_finds_the_classic_bugs(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text(textwrap.dedent("""
        import subprocess
        API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"
        def add(item, items=[]):
            items.append(item)
            return items
            print("never")
        def run(cmd):
            try:
                subprocess.run(cmd, shell=True)
            except:
                pass
            if cmd == None:
                eval(cmd)
    """))
    titles = " | ".join(x.title for x in static_review(f))
    for expected in ("hard-coded secret", "mutable default", "unreachable", "shell=True", "bare except",
                     "== None".replace("== None", "None with =="), "eval()"):
        assert expected in titles, expected
    llm = model([("Review this code change", json.dumps({"findings": [
        {"line": 4, "severity": "high", "title": "list shared between calls", "why": "x", "fix": "y"}]}))])
    found = review([f], llm)
    assert found[0].severity == "critical" and any(x.source == "model" for x in found)


# -- docs ------------------------------------------------------------------------
def test_doc_drift_and_generation(tmp_path):
    f = tmp_path / "m.py"
    f.write_text(textwrap.dedent('''
        def area(width, height):
            """Area.

            Args:
                w: the width.
                height: the height.

            Returns:
                float
            """
            return width * height

        def log(msg):
            """Log.

            Returns:
                nothing really
            """
            print(msg)

        def undocumented(x):
            return x
    '''))
    problems = {(d.name, d.problem) for d in docstring_drift(f)}
    assert ("area", "documents parameter 'w' that no longer exists") in problems
    assert ("area", "parameter 'width' is not documented") in problems
    assert ("log", "documents a return value but returns nothing") in problems
    md = tmp_path / "README.md"
    md.write_text("Use `area()` and `perimeter()`.\n")
    assert [d.name for d in markdown_drift(md, [f])] == ["perimeter"]
    new, n = add_docstrings(f.read_text(), model([("docstring", "Return x unchanged.\n\nArgs:\n    x: value.")]))
    assert n == 1 and 'def undocumented(x):\n    """Return x unchanged.' in new
    assert "## `area(width, height)`" in api_markdown(f)


# -- optimizer -------------------------------------------------------------------
SLOW = "def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n"
FAST = "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n"


def test_optimizer_keeps_only_faster_equal_code():
    r = optimize_function(SLOW, "fib", [[20], [22]], model([("measured hotspot", f"```python\n{FAST}```")]))
    assert r.accepted and r.same_results and r.speedup > 5
    wrong = optimize_function(SLOW, "fib", [[10]], model([("measured hotspot", "```python\ndef fib(n):\n    return 0\n```")]))
    assert not wrong.accepted and wrong.reason == "rejected: different results"
    assert benchmark(FAST, "fib", [[10]])["outs"] == ["55"]


def test_profiling_finds_the_hotspot(tmp_path):
    def slow():
        return sum(i * i for i in range(200000))

    _, spots = profile_call(slow)
    assert spots and spots[0].calls >= 1
    script = tmp_path / "s.py"
    script.write_text(SLOW + "fib(18)\n")
    assert profile_script(script)[0].function == "fib"


# -- polyglot --------------------------------------------------------------------
def test_detect_and_run_many_languages():
    assert detect("fn main() { println!(\"hi\"); }") == "rust"
    assert detect("package main\nfunc main() {}") == "go"
    assert detect("console.log(1)") == "javascript"
    assert detect("def f():\n    pass") == "python"
    assert run("print(input()[::-1])", "py", stdin="hola").stdout == "aloh\n"
    if "javascript" in available():
        assert run("console.log(2 + 3)", "js").stdout.strip() == "5"
    if "c" in available():
        assert run('#include <stdio.h>\nint main(){printf("%d", 6*7);}', "c").stdout == "42"
    assert not run("print(", "python").ok


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_translation_is_verified_by_running_both():
    py = "n = int(input())\nprint(sum(range(n + 1)))\n"
    llm = model([
        ("Translate this python", "```javascript\nconst n = 4;\nconsole.log(n);\n```"),  # wrong on purpose
        ("does not behave", "```javascript\nconst n = parseInt(require('fs').readFileSync(0, 'utf8'));\n"
                            "console.log(n * (n + 1) / 2);\n```"),
    ])
    t = translate(py, "js", llm, stdin_cases=("4", "10"))
    assert t.verified and t.rounds == 2 and t.source_language == "python"
