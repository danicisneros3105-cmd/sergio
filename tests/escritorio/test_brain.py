"""Mental gym exercises: every item is solvable and graded correctly."""

import random

import pytest
from sergio_escritorio import brain as b


@pytest.fixture
def rng():
    return random.Random(2026)


def test_the_ten_exercises_with_their_counts_and_times():
    plan = {e.kind: (e.items, e.seconds) for e in b.EXERCISES}
    assert plan == {
        "stroop": (15, 90),
        "calculo": (10, 90),
        "simetria": (20, 90),
        "nback": (1, 120),
        "relacional": (3, 120),
        "rotacion": (5, 120),
        "listas": (4, 120),
        "matrices": (2, 120),
        "palabras": (3, 120),
        "coordinacion": (5, 120),
    }
    first, nxt = b.next_exercise(9)
    assert first.kind == "coordinacion" and nxt == 0


def test_stroop_answers_the_ink(rng):
    items = [b.stroop(rng) for _ in range(200)]
    incongruent = sum(i.word != i.ink for i in items)
    assert 120 < incongruent < 180  # mostly conflicting, some congruent
    item = next(i for i in items if i.word != i.ink)
    assert item.check(item.ink.lower()) and not item.check(item.word)


def test_arithmetic_is_right(rng):
    for level in range(6):
        for _ in range(30):
            item = b.arithmetic(rng, level)
            expr = item.text.replace("×", "*").replace("÷", "//").replace("−", "-")
            if "%" in expr:
                p, base = expr.split("% de ")
                assert item.answer == int(p) * int(base) // 100
            else:
                assert eval(expr) == item.answer  # noqa: S307 — our own numbers
            assert item.check(str(item.answer)) and not item.check(str(item.answer + 1))


def test_symmetry_items_are_what_they_say(rng):
    for _ in range(300):
        item = b.symmetry(rng)
        assert b.is_symmetric(item.grid) == item.symmetric
        assert item.check("s") == item.symmetric and item.check("a") != item.symmetric


def test_relational_frames_follow_logic(rng):
    for _ in range(200):
        item = b.relational(rng)
        assert len(item.premises) == 4 and item.question.endswith("?")
        assert item.check("v") == item.answer and item.check("f") != item.answer


def test_relational_comparison_can_be_derived():
    """Solve the premises like a person would (transitivity)."""
    rng = random.Random(5)
    solved = 0
    for _ in range(100):
        item = b.relational(rng)
        if "más" not in item.question:
            continue
        bigger = set()
        for line in item.premises:
            words = line.rstrip(".").split()
            a, rel, c = words[0], words[3], words[-1]
            bigger.add((a, c) if rel == "grande" else (c, a))
        changed = True
        while changed:
            changed = False
            for (p, q) in list(bigger):
                for (r, s) in list(bigger):
                    if q == r and (p, s) not in bigger:
                        bigger.add((p, s))
                        changed = True
        words = item.question.strip("¿?").split()
        x, rel, y = words[0], words[3], words[-1]
        truth = (x, y) in bigger if rel == "grande" else (y, x) in bigger
        assert truth == item.answer
        solved += 1
    assert solved > 30


def test_mental_rotation_has_one_true_twin(rng):
    for _ in range(25):
        item = b.rotation(rng)
        ref = b.canonical(item.reference)
        matches = [i for i, o in enumerate(item.options) if b.canonical(o) == ref]
        assert matches == [item.answer]  # the others are mirror images or other shapes
        assert item.check(str(item.answer + 1))
        assert b.canonical(item.reference) != b.canonical(b.mirror(item.reference))


def test_matrices_have_a_unique_answer(rng):
    for _ in range(60):
        item = b.matrix(rng)
        assert len(item.options) == 6 and len(set(item.options)) == 6
        assert item.options[item.answer] == item.cells[-1]
        right = item.cells[-1]
        for i, option in enumerate(item.options):
            if i != item.answer:
                diffs = sum(
                    getattr(option, a) != getattr(right, a)
                    for a in ("shape", "count", "shade", "turn")
                )
                assert diffs >= 1


def test_reversed_lists(rng):
    item = b.ListItem(["7", "3", "9", "1"])
    assert item.check("1937") and item.check("1 9 3 7") and not item.check("7391")
    assert item.partial("19") == 0.5
    words = b.ListItem(["sol", "mar", "río"])
    assert words.check("rio mar sol") and words.check("Río, mar, sol")
    assert len(b.reversed_list(rng, 7).items) == 7


def test_restricted_words(rng):
    ch = b.WordChallenge("animales", "empiezan con «c»", ("starts", "c"))
    assert ch.judge("Caballo") == "ok"
    assert ch.judge("perro") == "regla"
    assert ch.judge("cucurucho") == "desconocida"
    assert ch.judge("Cóndor") == "ok"  # accents don't matter
    country = b.WordChallenge("paises", "tienen más de 7 letras", ("longer", 7))
    assert country.judge("nueva zelanda") == "ok"
    for _ in range(50):
        challenge = b.word_challenge(rng)
        valid = [w for w in b.CATEGORIES[challenge.category] if challenge.fits(w)]
        assert len(valid) >= 6 and all(challenge.fits(e) for e in challenge.examples)


def test_coordination_sequences(rng):
    item = b.coordination(rng, 6, chords=2)
    assert len(item.steps) == 6 and sum(len(s) == 2 for s in item.steps) == 2
    for chord in (s for s in item.steps if len(s) == 2):
        assert chord[0] in "df" and chord[1] in "jk"  # one key per hand
    assert item.check(list(item.steps))
    wrong = list(item.steps)
    wrong[3] = ("x",)
    assert not item.check(wrong) and item.partial(wrong) == 0.5


def test_nback_adapts_up_and_down(rng):
    good = b.NBack(rng, level=2)
    for _ in range(24):
        trial = good.next()
        good.answer(trial.position_match, trial.letter_match)  # perfect
    assert good.level == 4 and good.accuracy == 1.0
    bad = b.NBack(random.Random(1), level=3)
    for _ in range(12):
        trial = bad.next()
        bad.answer(not trial.position_match, not trial.letter_match)  # all wrong
    assert bad.level == 2
    # targets really refer to n steps back
    nb = b.NBack(random.Random(3), level=2)
    trials = [nb.next() for _ in range(40)]
    for i, t in enumerate(trials[2:], start=2):
        assert t.position_match == (t.position == trials[i - 2].position)
    assert 0.1 < sum(t.position_match for t in trials) / 40 < 0.5


def test_session_summary():
    s = b.Session(b.BY_KIND["stroop"])
    for ok in [1] * 12 + [0] * 3:
        s.record(ok, 1.2)
    assert s.summary() == "12 de 15, 1.2 s por respuesta."
    assert s.verdict() == "Muy bien."
