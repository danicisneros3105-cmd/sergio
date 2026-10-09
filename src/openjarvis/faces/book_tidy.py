"""Keeping the face book clean: sample sharpness, adding samples, checking a
sample belongs to the same person, scoring and purifying a gallery.

Split out of ``book.py``; its names are looked up on that module at call
time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any

import openjarvis.faces.book as _book


def _sharpness(aligned: Any) -> float:
    """How sharp a face crop is (variance of the Laplacian)."""
    try:
        import cv2

        grey = (
            cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY) if aligned.ndim == 3 else aligned
        )
        return float(cv2.Laplacian(grey, cv2.CV_64F).var())
    except Exception:  # noqa: BLE001 — a missing measure only changes the order
        return 0.0


def _column(person: dict[str, Any], key: str, count: int) -> list[Any]:
    """A per-photo list (signatures, poses, sources), as long as the photos."""
    values = list(person.get(key) or [])[:count]
    return values + [None] * (count - len(values))


def _add_samples(
    person: dict[str, Any], items: list[tuple[Any, Any, Any, str]]
) -> None:
    """Append (embedding, signature, pose, source) photos, then trim to
    MAX_SAMPLES: photos it learnt by itself go first, then plain photos,
    and the scan's angles last (they are what covers the whole head)."""
    count = len(person.get("embeddings") or [])
    columns = {
        "embeddings": list(person.get("embeddings") or []),
        "signatures": _book._column(person, "signatures", count),
        "poses": _book._column(person, "poses", count),
        "sources": [x or "foto" for x in _book._column(person, "sources", count)],
    }
    for embedding, signature, pose, source in items:
        columns["embeddings"].append(list(embedding))
        columns["signatures"].append(signature)
        columns["poses"].append(list(pose) if pose is not None else None)
        columns["sources"].append(source)
    while len(columns["embeddings"]) > _book.MAX_SAMPLES:
        sources = columns["sources"]
        drop = next(
            (
                i
                for kind in ("auto", "foto", "escaneo")
                for i, x in enumerate(sources)
                if x == kind
            ),
            0,
        )
        for values in columns.values():
            del values[drop]
    person.update(columns)


def _check_same_person(people: dict[str, Any], name: str, feature: Any) -> None:
    """A new photo of *name* must look like *name*, and not like someone else
    already saved: one wrong photo used to make everyone "Daniel"."""
    import numpy as np

    known = (people.get(name) or {}).get("embeddings") or []
    own = (
        _book.person_score(feature, np.asarray(known, dtype=np.float32))
        if known
        else None
    )
    if own is not None and len(known) >= 2 and own < _book.SAME_PERSON_MIN:
        raise _book.FaceError(
            f"Esa cara no parece de {name} (parecido {own:.2f}). Si es "
            "otra persona, guárdala con su propio nombre."
        )
    for other, person in people.items():
        if other == name or not person.get("embeddings"):
            continue
        theirs = _book.person_score(
            feature, np.asarray(person["embeddings"], dtype=np.float32)
        )
        # Near-certain only (siblings sit lower): twins can still be saved.
        if theirs >= _book.STRONG_MATCH and (
            own is None or theirs > own + _book.MATCH_MARGIN
        ):
            raise _book.FaceError(
                f"Esa cara ya está guardada como {other} (parecido {theirs:.2f}). "
                f"Si de verdad es {name}, que se ponga frente a la cámara a solas."
            )


def person_score(feature: Any, embeddings: Any) -> float:
    """How much a face looks like a person: mean of their best TOP_K photos."""
    import numpy as np

    scores = np.sort(embeddings @ feature)[::-1]
    return float(np.mean(scores[: _book.TOP_K]))


def purify(
    embeddings: list, *columns: list, together: list[int] | None = None
) -> tuple[list, ...]:
    """Keep only one person's photos: the biggest group of photos that look
    alike (ties: the group with the oldest photo, the one enrolled first).
    Repairs a person that got other people's faces saved under their name.
    *columns* (signatures, poses, ...) are filtered the same way.
    *together*: photos known to be one person (a scan: one continuous head
    turn); a profile looks little like a front photo, but it is not a
    stranger."""
    import numpy as np

    n = len(embeddings)
    if n < 3:
        return (embeddings, *columns)
    e = np.asarray(embeddings, dtype=np.float32)
    e = e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9)
    linked = (e @ e.T) >= _book.CLUSTER_LINK
    if together:
        idx = [i for i in together if 0 <= i < n]
        linked[np.ix_(idx, idx)] = True
    group = [-1] * n
    for start in range(n):
        if group[start] >= 0:
            continue
        group[start], stack = start, [start]
        while stack:
            i = stack.pop()
            for j in np.flatnonzero(linked[i]):
                if group[j] < 0:
                    group[j] = start
                    stack.append(int(j))
    sizes = {g: group.count(g) for g in set(group)}
    keep = max(sizes, key=lambda g: (sizes[g], -g))
    if sizes[keep] == n:
        return (embeddings, *columns)
    idx = [i for i in range(n) if group[i] == keep]
    return (
        [embeddings[i] for i in idx],
        *([column[i] for i in idx] for column in columns),
    )


def _tidy(people: dict[str, Any]) -> dict[str, Any]:
    """Clean names ('Daniel Cisneros .' -> 'Daniel Cisneros'), merging twins,
    and drop faces of other people saved by mistake under a name."""
    out: dict[str, Any] = {}
    for raw, person in people.items():
        name = _book.clean_name(raw) or raw
        key = next((k for k in out if k.lower() == name.lower()), name)
        embs = list(person.get("embeddings") or [])
        cols = {c: _book._column(person, c, len(embs)) for c in _book.COLUMNS}
        if key in out:
            out[key]["embeddings"] = out[key]["embeddings"] + embs
            for c in _book.COLUMNS:
                out[key][c] = out[key][c] + cols[c]
            for extra in ("mesh3d", "scanned_at"):
                if person.get(extra) and not out[key].get(extra):
                    out[key][extra] = person[extra]
        else:
            out[key] = {**person, "embeddings": embs, **cols}
    for person in out.values():
        try:
            scanned = [i for i, x in enumerate(person["sources"]) if x == "escaneo"]
            embs, *cols = _book.purify(
                person["embeddings"],
                *(person[c] for c in _book.COLUMNS),
                together=scanned,
            )
            person["embeddings"] = embs
            person.update(dict(zip(_book.COLUMNS, cols)))
        except (ValueError, TypeError):  # odd shapes: leave as they are
            pass
        if (
            len(person["embeddings"]) > _book.MAX_SAMPLES
        ):  # merged twins: trim like new photos
            extra = person["embeddings"]
            person["embeddings"] = []
            cols = {c: person[c] for c in _book.COLUMNS}
            for c in _book.COLUMNS:
                person[c] = []
            _book._add_samples(
                person,
                [
                    (
                        extra[i],
                        cols["signatures"][i],
                        cols["poses"][i],
                        cols["sources"][i] or "foto",
                    )
                    for i in range(len(extra))
                ],
            )
    return out


__all__ = [
    "_sharpness",
    "_column",
    "_add_samples",
    "_check_same_person",
    "person_score",
    "purify",
    "_tidy",
]
