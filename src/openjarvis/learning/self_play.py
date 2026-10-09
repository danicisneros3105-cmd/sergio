"""Layer 10 — Self-Play Curriculum: practise on problems that check themselves.

A generator makes problems whose answers can be verified by code — exact
arithmetic, number sequences, ordering puzzles, small programming tasks run
against hidden tests — at a difficulty level per domain. The solver (the
model) attempts a batch; the verifier marks each one. Like a coach, the
curriculum moves a domain up a level when the success rate is high and down
when it is low, so practice stays at the edge of ability. Failures become
lessons in long-term memory (when given) so later answers improve.

A second mode, ``propose_and_solve``, is true self-play: the model invents
a problem with its answer, then solves it fresh; only problems whose two
answers agree are kept for practice.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from openjarvis.intelligence._llm import LLM, as_llm, parse_json
from openjarvis.intelligence.consistency import extract_final, normalise

Solver = Callable[[str], str]


@dataclass
class Problem:
    domain: str
    level: int
    prompt: str
    answer: str = ""
    tests: list[tuple[str, str]] = field(
        default_factory=list
    )  # code: (call, expected repr)


# -- generators (difficulty 1..10) ---------------------------------------------
def gen_arithmetic(level: int, rng: random.Random) -> Problem:
    terms = 2 + level
    hi = 10 ** min(1 + level // 2, 5)
    nums = [rng.randint(1, hi) for _ in range(terms)]
    ops = [rng.choice("+-*" if level > 3 else "+-") for _ in range(terms - 1)]
    expr = str(nums[0]) + "".join(f" {o} {n}" for o, n in zip(ops, nums[1:]))
    if level >= 6:
        expr = f"({expr}) % {rng.randint(7, 97)}"
    value = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 — our own digits and operators only
    return Problem("arithmetic", level, f"Compute exactly: {expr}", str(value))


def gen_sequence(level: int, rng: random.Random) -> Problem:
    start, step = rng.randint(1, 9), rng.randint(2, 3 + level)
    kind = rng.choice(["add", "mul", "square", "fib"][: 1 + min(3, level // 2)])
    seq: list[int] = []
    if kind == "add":
        seq = [start + step * i for i in range(6)]
    elif kind == "mul":
        seq = [start * (2 if level < 5 else step) ** i for i in range(6)]
    elif kind == "square":
        seq = [(start + i) ** 2 + (level - 3) for i in range(6)]
    else:
        a, b = start, start + step
        for _ in range(6):
            seq.append(a)
            a, b = b, a + b
    shown = ", ".join(map(str, seq[:5]))
    return Problem(
        "sequence", level, f"What number comes next: {shown}, ?", str(seq[5])
    )


NAMES = [
    "Ana",
    "Luis",
    "Marta",
    "Pedro",
    "Sofía",
    "Diego",
    "Elena",
    "Jorge",
    "Lucía",
    "Raúl",
]


def gen_ordering(level: int, rng: random.Random) -> Problem:
    n = min(3 + level // 2, len(NAMES))
    people = rng.sample(NAMES, n)  # tallest first
    clues = [f"{people[i]} is taller than {people[i + 1]}." for i in range(n - 1)]
    rng.shuffle(clues)
    ask_last = rng.random() < 0.5
    question = "Who is the shortest?" if ask_last else "Who is the tallest?"
    return Problem(
        "ordering",
        level,
        " ".join(clues) + " " + question,
        people[-1] if ask_last else people[0],
    )


CODE_TASKS = [
    (
        1,
        "Write a Python function `double(x)` that returns x times two.",
        "double",
        [("double(3)", "6"), ("double(-2)", "-4")],
    ),
    (
        2,
        "Write a Python function `is_even(n)` returning True when n is even.",
        "is_even",
        [("is_even(4)", "True"), ("is_even(7)", "False")],
    ),
    (
        3,
        "Write a Python function `reverse_words(s)` that reverses the order of the words in s.",
        "reverse_words",
        [("reverse_words('a b c')", "'c b a'"), ("reverse_words('hola')", "'hola'")],
    ),
    (
        4,
        "Write a Python function `count_vowels(s)` counting a, e, i, o, u (any case).",
        "count_vowels",
        [("count_vowels('Hello World')", "3"), ("count_vowels('xyz')", "0")],
    ),
    (
        5,
        "Write a Python function `fizzbuzz(n)` returning 'Fizz' for multiples of 3, 'Buzz' for 5, "
        "'FizzBuzz' for both, else str(n).",
        "fizzbuzz",
        [
            ("fizzbuzz(15)", "'FizzBuzz'"),
            ("fizzbuzz(9)", "'Fizz'"),
            ("fizzbuzz(7)", "'7'"),
        ],
    ),
    (
        6,
        "Write a Python function `flatten(xs)` that flattens arbitrarily nested lists.",
        "flatten",
        [("flatten([1,[2,[3,[4]]]])", "[1, 2, 3, 4]"), ("flatten([])", "[]")],
    ),
    (
        7,
        "Write a Python function `is_balanced(s)` that checks that (), [] and {} are balanced.",
        "is_balanced",
        [
            ("is_balanced('([]{})')", "True"),
            ("is_balanced('(]')", "False"),
            ("is_balanced('((')", "False"),
        ],
    ),
    (
        8,
        "Write a Python function `lis(xs)` returning the length of the longest strictly increasing "
        "subsequence.",
        "lis",
        [("lis([10,9,2,5,3,7,101,18])", "4"), ("lis([])", "0")],
    ),
    (
        9,
        "Write a Python function `roman(n)` converting 1..3999 to Roman numerals.",
        "roman",
        [("roman(1994)", "'MCMXCIV'"), ("roman(4)", "'IV'")],
    ),
    (
        10,
        "Write a Python function `edit_distance(a, b)` (Levenshtein).",
        "edit_distance",
        [("edit_distance('kitten','sitting')", "3"), ("edit_distance('','abc')", "3")],
    ),
]


def gen_code(level: int, rng: random.Random) -> Problem:
    options = [t for t in CODE_TASKS if t[0] <= level] or CODE_TASKS[:1]
    lvl, text, _name, tests = (
        max(options, key=lambda t: (t[0], rng.random()))
        if rng.random() < 0.6
        else rng.choice(options)
    )
    return Problem("code", lvl, text + " Reply with only the code.", tests=list(tests))


GENERATORS: dict[str, Callable[[int, random.Random], Problem]] = {
    "arithmetic": gen_arithmetic,
    "sequence": gen_sequence,
    "ordering": gen_ordering,
    "code": gen_code,
}


# -- verification --------------------------------------------------------------
def _code_from(text: str) -> str:
    fence = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return textwrap.dedent(fence.group(1) if fence else text)


def run_code_tests(
    code: str, tests: list[tuple[str, str]], timeout: float = 10.0
) -> tuple[bool, str]:
    """Run *code* plus asserts in a separate, isolated Python with a timeout."""
    checks = "\n".join(
        f"assert repr({call}) == {expected!r}, {call!r}" for call, expected in tests
    )
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "solution.py"
        script.write_text(code + "\n\n" + checks + "\nprint('ALL_OK')\n", "utf-8")
        try:
            out = subprocess.run(
                [sys.executable, "-I", str(script)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout:.0f} s"
    ok = out.returncode == 0 and "ALL_OK" in out.stdout
    return ok, "" if ok else (out.stderr.strip().splitlines() or ["failed"])[-1][:300]


def verify(problem: Problem, reply: str) -> tuple[bool, str]:
    if problem.domain == "code":
        return run_code_tests(_code_from(reply), problem.tests)
    got = normalise(extract_final(reply))
    want = normalise(problem.answer)
    ok = (
        got == want
        or re.search(rf"(?<![\w.]){re.escape(want)}(?![\w.])", got) is not None
    )
    return (
        ok,
        "" if ok else f"expected {problem.answer}, got {extract_final(reply)[:80]}",
    )


SOLVE_PROMPT = "{prompt}\n\nThink briefly, then end with: FINAL ANSWER: <answer>"


def llm_solver(llm: "LLM | Callable[..., str] | None" = None) -> Solver:
    model = as_llm(llm)

    def solve(prompt: str) -> str:
        if "Reply with only the code" in prompt:
            return model(prompt, temperature=0.2)
        return model(SOLVE_PROMPT.format(prompt=prompt), temperature=0.2)

    return solve


# -- the curriculum ------------------------------------------------------------
@dataclass
class Curriculum:
    levels: dict[str, int] = field(default_factory=lambda: {d: 1 for d in GENERATORS})
    history: list[dict] = field(default_factory=list)
    up: float = 0.8
    down: float = 0.4

    def adjust(self, domain: str, rate: float) -> int:
        level = self.levels.get(domain, 1)
        if rate >= self.up:
            level = min(10, level + 1)
        elif rate < self.down:
            level = max(1, level - 1)
        self.levels[domain] = level
        return level

    @classmethod
    def load(cls, path: Path) -> "Curriculum":
        try:
            data = json.loads(path.read_text("utf-8"))
            return cls(
                levels={**{d: 1 for d in GENERATORS}, **data.get("levels", {})},
                history=data.get("history", []),
            )
        except (OSError, ValueError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["history"] = data["history"][-500:]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def practice(
    solver: Solver,
    *,
    domains: Optional[list[str]] = None,
    rounds: int = 3,
    batch: int = 5,
    curriculum: Optional[Curriculum] = None,
    seed: Optional[int] = None,
    memory: object = None,
) -> Curriculum:
    """Run *rounds* of practice; each round adjusts every domain's level."""
    rng = random.Random(seed)
    cur = curriculum or Curriculum()
    for rnd in range(rounds):
        for domain in domains or list(GENERATORS):
            level = cur.levels.get(domain, 1)
            passed = 0
            for _ in range(batch):
                problem = GENERATORS[domain](level, rng)
                try:
                    reply = solver(problem.prompt)
                    ok, why = verify(problem, reply)
                except Exception as exc:  # noqa: BLE001 — a crash is a failed attempt
                    ok, why = False, f"solver error: {exc}"
                passed += ok
                if not ok and memory is not None and hasattr(memory, "remember"):
                    memory.remember(
                        "lesson",
                        f"Práctica ({domain}, nivel {level}) fallada: {problem.prompt[:200]} "
                        f"— {why}",
                        source="self_play",
                    )
            rate = passed / batch
            new_level = cur.adjust(domain, rate)
            cur.history.append(
                {
                    "round": rnd + 1,
                    "domain": domain,
                    "level": level,
                    "rate": round(rate, 3),
                    "next_level": new_level,
                }
            )
    return cur


PROPOSE_PROMPT = """Invent one {domain} problem of difficulty {level}/10 whose answer is a
single short value that can be checked exactly. Reply with JSON only:
{{"problem": "...", "answer": "..."}}"""


def propose_and_solve(
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    domain: str = "logic",
    level: int = 3,
    count: int = 3,
) -> list[Problem]:
    """Self-play: the model sets problems and then solves them blind; only
    problems whose blind answer matches the setter's answer are kept."""
    model = as_llm(llm)
    solve = llm_solver(model)
    kept: list[Problem] = []
    for _ in range(count):
        data = parse_json(
            model(PROPOSE_PROMPT.format(domain=domain, level=level), temperature=1.0)
        )
        if (
            not isinstance(data, dict)
            or not data.get("problem")
            or not str(data.get("answer", "")).strip()
        ):
            continue
        problem = Problem(domain, level, str(data["problem"]), str(data["answer"]))
        ok, _ = verify(problem, solve(problem.prompt))
        if ok:
            kept.append(problem)
    return kept


__all__ = [
    "CODE_TASKS",
    "Curriculum",
    "GENERATORS",
    "Problem",
    "llm_solver",
    "practice",
    "propose_and_solve",
    "run_code_tests",
    "verify",
]
