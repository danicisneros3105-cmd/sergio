"""Goals, medications and reminders: what Sergio keeps for the owner.

One small local store (:mod:`store`) for the three kinds:

* **medicina** — a medication with its dose and times; each dose can be
  marked taken or skipped, so the adherence of the week is real;
* **meta** — a goal with its why and a check-in time; Sergio keeps the
  active goals in mind in every conversation (:func:`goals_block`);
* **recordatorio** — anything else at a time or on some days.

They are notifications for the owner himself: Sergio never sends anything
to anyone because of them. Nothing here is medical advice.
"""

from openjarvis.reminders.store import (
    KINDS,
    ReminderStore,
    get_store,
    goals_block,
)

__all__ = ["KINDS", "ReminderStore", "get_store", "goals_block"]
