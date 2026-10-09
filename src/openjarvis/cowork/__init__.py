"""Cowork mode: describe an outcome, step away, Sergio does the rest.

See :mod:`openjarvis.cowork.session` (runs), :mod:`openjarvis.cowork.scrutiny`
(what may run on its own) and :mod:`openjarvis.cowork.audit` (the trail).
"""

from __future__ import annotations

from openjarvis.cowork.audit import AuditTrail
from openjarvis.cowork.scrutiny import AXES, AdaptiveScrutiny, TrustStore, Verdict
from openjarvis.cowork.session import (
    DEFAULT_MAX_ACTIONS,
    ActionBudget,
    BudgetExhausted,
    CoworkEngine,
    CoworkRun,
    CoworkStep,
)

__all__ = [
    "AXES",
    "ActionBudget",
    "AdaptiveScrutiny",
    "AuditTrail",
    "BudgetExhausted",
    "CoworkEngine",
    "CoworkRun",
    "CoworkStep",
    "DEFAULT_MAX_ACTIONS",
    "TrustStore",
    "Verdict",
]
