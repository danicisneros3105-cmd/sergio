"""Intelligence learning — model fine-tuning via SFT and GRPO."""

from __future__ import annotations

import logging as _logging

# Import trainers so their @LearningRegistry.register decorators execute.
try:
    from openjarvis.learning.intelligence import sft_trainer as _sft  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.learning.intelligence): %s", _exc
    )
try:
    from openjarvis.learning.intelligence import grpo_trainer as _grpo  # noqa: F401
except ImportError as _exc:
    _logging.getLogger(__name__).debug(
        "Optional import skipped (openjarvis.learning.intelligence): %s", _exc
    )
