"""XML from outside (news feeds, backup servers) parsed without surprises.

ElementTree never fetches external entities and Python's expat (2.4+) stops
the "billion laughs" expansion, but a feed has no business declaring a
DOCTYPE or entities at all: :func:`fromstring` refuses them before parsing,
so neither trick nor a future parser change can reach Sergio through a feed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Union

_DECLARATION = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
MAX_BYTES = 20 * 1024 * 1024


class UnsafeXML(ValueError):
    pass


def fromstring(data: Union[str, bytes]) -> ET.Element:
    raw = data.encode("utf-8", "replace") if isinstance(data, str) else data
    if len(raw) > MAX_BYTES:
        raise UnsafeXML("XML demasiado grande")
    if _DECLARATION.search(raw):
        raise UnsafeXML("XML con declaraciones DOCTYPE o ENTITY")
    return ET.fromstring(raw)


__all__ = ["UnsafeXML", "fromstring"]
