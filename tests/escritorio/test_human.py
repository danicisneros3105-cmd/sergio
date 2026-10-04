"""Mouse and keyboard like a person: curved, eased moves and uneven typing."""

import math
import random

from sergio_escritorio.human import human_path, move_seconds, typing_delays


def test_path_ends_exactly_on_target_and_is_curved_and_eased():
    rng = random.Random(3)
    path = human_path((100, 100), (700, 400), rng)
    t_end, x_end, y_end = path[-1]
    assert (x_end, y_end) == (700, 400)
    assert 0.25 < t_end < 1.3

    # not a straight line: some point is well off the direct segment
    def off_line(x, y):
        return abs(
            (400 - 100) * x - (700 - 100) * y + 700 * 100 - 400 * 100
        ) / math.hypot(300, 600)

    assert max(off_line(x, y) for _t, x, y in path) > 10
    # slow start, fast middle, gentle stop (minimum-jerk)
    steps = [math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(path, path[1:])]
    third = len(steps) // 3
    assert sum(steps[third : 2 * third]) > sum(steps[:third])


def test_far_targets_take_longer_like_fitts_law():
    rng = random.Random(1)
    near = sum(move_seconds(50, rng) for _ in range(50)) / 50
    far = sum(move_seconds(1500, rng) for _ in range(50)) / 50
    assert far > near * 1.5


def test_typing_rhythm_is_human_and_uneven():
    text = "Hola, ¿cómo estás? Ñandú."
    delays = typing_delays(text, random.Random(2))
    assert len(delays) == len(text)
    assert 0.04 < sum(delays) / len(delays) < 0.25  # 40-250 ms a key
    assert len({round(d, 3) for d in delays}) > len(delays) // 2  # not robotic
    long = typing_delays("x" * 600, random.Random(2))
    assert sum(long) / len(long) < sum(delays) / len(delays)  # long texts: faster
