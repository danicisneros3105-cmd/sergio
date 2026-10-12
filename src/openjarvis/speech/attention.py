"""Bounded conversational attention, without pretending to identify people.

Speech recognition is not authentication. This policy only decides whether
Sergio should answer: his name opens a follow-up window; explicit room
conversation closes it. Known speaker changes require a fresh address.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Callable


def normalized(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    )


class Attention:
    def __init__(
        self,
        name: str = "Sergio",
        *,
        window: float = 90,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = re.escape(normalized(name))
        self.clock, self.window = clock, window
        self.until = clock() + window  # opening a call explicitly addresses him
        self.other_speaker = False

    def speaker(self, owner: bool) -> None:
        self.other_speaker = not owner
        self.until = 0

    def accepts(self, text: str) -> bool:
        text = normalized(text)
        if re.search(
            r"\b(no te hablo|no era para ti|hablo con otra persona|"
            r"estoy hablando por telefono|no te estoy hablando)\b",
            text,
        ):
            self.until = 0
            return False
        # Mentioning him in the third person is not calling him.
        named = re.search(rf"\b{self.name}\b", text) is not None
        mention = re.search(rf"\b{self.name}\s+(dijo|dice|es|hizo|me dijo)\b", text)
        if named and not mention:
            self.until = self.clock() + self.window
            return True
        if mention or self.other_speaker or self.clock() >= self.until:
            return False
        self.until = self.clock() + self.window
        return True


__all__ = ["Attention"]
