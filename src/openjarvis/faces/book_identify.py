"""FaceBook's recognition side: scanning a frame, identifying faces live or
in a photo, kinship estimates and learning from confirmed matches.

Split out of ``book.py``; its names are looked up on that module at call
time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any

import openjarvis.faces.book as _book


class _IdentifyMixin:
    def scan(
        self,
        name: str,
        images: list[bytes],
        *,
        consent: bool,
        mesh: dict[str, Any] | None = None,
        replace: bool = False,
    ) -> dict[str, Any]:
        """A Face ID-style scan: one person turning their head slowly in a
        circle. The sharpest photos of each head angle are kept, so Sergio
        knows the face from the front, the sides, above and below (and the
        3D map of its 478 points, in millimetres, when the companion sends it).
        ``replace`` starts the person again (a fresh setup), so old, poor
        samples can never make the new scan fail.
        """
        import numpy as np

        raw = (name or "").strip()
        name = _book.clean_name(raw)
        if not consent:
            raise _book.FaceError(
                "Enroll a person only with their consent (confirm consent=true)."
            )
        if not _book._RAW_NAME.match(raw) or not _book._NAME.match(name):
            raise _book.FaceError(
                "Use a plain name (letters, spaces, up to 60 characters)."
            )
        shots = []
        for data in images[:80]:
            try:
                found = self._faces(data, old=False)
            except _book.FaceError:
                continue
            if not found:
                continue
            found = sorted(found, key=lambda f: f[1][2] * f[1][3], reverse=True)
            feature, box, *rest = found[0]
            if (
                len(found) > 1
                and found[1][1][2] * found[1][1][3] > 0.5 * box[2] * box[3]
            ):
                continue  # two people in the shot: not a scan of one face
            detection = float(rest[0]) if rest else 1.0
            if (
                min(box[2], box[3]) < _book.MIN_FACE_PX
                or detection < _book.SCAN_MIN_DETECTION
            ):
                continue
            pose = tuple(rest[1]) if len(rest) > 1 else (0.0, 0.0)
            sharp = float(rest[2]) if len(rest) > 2 else 0.0
            shots.append((feature, pose, sharp))
        if len(shots) < 3:
            raise _book.FaceError(
                "No vi la cara con claridad durante el escaneo: más luz, la cara "
                "entera en la cámara y gira la cabeza despacio."
            )
        front = [f for f, pose, _ in shots if _book.angle_of(pose) == "C-M"] or [
            f for f, _, _ in shots
        ]
        centre = np.mean(np.asarray(front, dtype=np.float32), axis=0)
        centre /= np.linalg.norm(centre) + 1e-9
        shots = [
            x for x in shots if float(np.dot(x[0], centre)) >= _book.SCAN_CONSISTENT
        ]
        best: dict[str, list[tuple[Any, tuple[float, float], float]]] = {}
        for shot in sorted(shots, key=lambda x: -x[2]):
            kept = best.setdefault(_book.angle_of(shot[1]), [])
            if len(kept) < _book.SCAN_PER_ANGLE:
                kept.append(shot)
        if len(best) < _book.SCAN_MIN_ANGLES:
            raise _book.FaceError(
                f"Solo vi {len(best)} ángulo(s) de la cara: gira la cabeza despacio "
                "en círculo (izquierda, arriba, derecha, abajo) mientras te escaneo."
            )
        with self._lock:
            people = self._load(strict=True)
            name = next((k for k in people if k.lower() == name.lower()), name)
            if replace:
                people.pop(name, None)
            _book._check_same_person(people, name, centre)
            person = people.setdefault(
                name, {"embeddings": [], "enrolled_at": _book.time.time()}
            )
            added = [
                (f.tolist(), None, pose, "escaneo")
                for angle in sorted(best)
                for f, pose, _ in best[angle]
            ]
            _book._add_samples(person, added)
            person["scanned_at"] = _book.time.time()
            if isinstance(mesh, dict) and mesh.get("points"):
                person["mesh3d"] = mesh
            self._save(people)
            total = len(person["embeddings"])
        return {
            "name": name,
            "samples": total,
            "added": len(added),
            "angles": sorted(best),
            "words": [_book.ANGLE_WORDS.get(a, a) for a in sorted(best)],
        }

    def _person_signatures(self) -> dict[str, list[float]]:
        """Each person's mean signature (their stable proportions)."""
        out = {}
        for name, p in self._load().items():
            sigs = [g for g in p.get("signatures") or [] if g]
            if sigs:
                out[name] = [sum(col) / len(sigs) for col in zip(*sigs)]
        return out

    def identify_photo(
        self, image_bytes: bytes, faces: list[dict] | None = None
    ) -> list[_book.Match]:
        """Who is in a photo (also an old, faded or scanned one).

        Same decision as the camera, plus the three best guesses and the
        likeness of the 175 measurements for each face.
        """
        from openjarvis.faces.signature import similarity

        image = self._decode(image_bytes)
        old = _book.looks_old(image)
        matches = self.identify(image_bytes, old=old, candidates=3)
        if matches:
            signatures = self._person_signatures()
            seen = _book.enhance(image) if old else image
            for m in matches:
                geometry = self._measured(m.box, faces) or self._signature(seen, m.box)
                best = m.name or (m.candidates[0][0] if m.candidates else "")
                if geometry is not None and best in signatures:
                    m.geometry = similarity(geometry, signatures[best])
        return matches

    def kinship(
        self, image_bytes: bytes, faces: list[dict] | None = None
    ) -> list[dict[str, Any]]:
        """Family resemblance of each face in the photo with everyone enrolled."""
        import numpy as np

        from openjarvis.faces.signature import similarity

        image = self._decode(image_bytes)
        old = _book.looks_old(image)
        seen = _book.enhance(image) if old else image
        found = self._faces_in(seen)
        people = {
            name: np.asarray(p["embeddings"], dtype=np.float32)
            for name, p in self._load().items()
            if p.get("embeddings")
        }
        signatures = self._person_signatures()
        out = []
        for feature, box, _score in found:
            geometry = self._measured(box, faces) or self._signature(seen, box)
            ranked = []
            for name, embs in people.items():
                deep = _book.person_score(feature, embs)
                geo = (
                    similarity(geometry, signatures[name])
                    if geometry is not None and name in signatures
                    else None
                )
                same = deep >= _book.MATCH_THRESHOLD
                kin = _book.kin_score(deep, geo)
                ranked.append(
                    {
                        "name": name,
                        "same_person": same,
                        "deep": round(deep, 3),
                        "geometry": None if geo is None else round(geo, 3),
                        "kin": round(kin, 3),
                        "words": "es la misma persona"
                        if same
                        else _book.kin_words(kin),
                    }
                )
            ranked.sort(key=lambda r: (r["same_person"], r["kin"]), reverse=True)
            out.append({"box": list(box), "old_photo": old, "people": ranked})
        return out

    def identify(
        self,
        image_bytes: bytes,
        *,
        old: bool | None = False,
        candidates: int = 0,
        learn: bool = False,
    ) -> list[_book.Match]:
        """Who is in the image. *learn*: a face it is very sure of, seen from
        an angle it has few photos of, becomes one more photo of that person
        (it keeps learning your face while it sees you)."""
        faces = self._faces(image_bytes, old=old)
        people = self._gallery()
        matches = []
        for feature, box, *rest in faces:
            detection = float(rest[0]) if rest else 1.0
            pose = tuple(rest[1]) if len(rest) > 1 else (0.0, 0.0)
            ranked = sorted(
                (
                    (_book.person_score(feature, embs), name)
                    for name, embs in people.items()
                ),
                reverse=True,
            )
            best, name = ranked[0] if ranked else (0.0, "")
            runner_up = ranked[1][0] if len(ranked) > 1 else -1.0
            margin = best - max(runner_up, 0.0)
            quality = "ok"
            if min(box[2], box[3]) < _book.MIN_FACE_PX:
                quality = "pequeña"
            elif detection < _book.MIN_DETECTION:
                quality = "borrosa"
            sure = (
                quality == "ok"
                and best >= _book.MATCH_THRESHOLD
                and best - runner_up >= _book.MATCH_MARGIN
            )
            guesses = (
                [(n, max(v, 0.0)) for v, n in ranked[:candidates]]
                if candidates
                else None
            )
            if sure:
                match = _book.Match(
                    name,
                    best,
                    box,
                    quality=quality,
                    candidates=guesses,
                    margin=margin,
                    pose=pose,
                )
                if (
                    learn
                    and best >= _book.LEARN_MIN
                    and margin >= _book.LEARN_MARGIN
                    and min(box[2], box[3]) >= _book.LEARN_MIN_PX
                ):
                    match.learned = self._learn(name, feature, pose)
                matches.append(match)
            else:
                guest = self._guests.number(feature) if quality == "ok" else 0
                matches.append(
                    _book.Match(
                        "",
                        max(best, 0.0),
                        box,
                        guest,
                        quality,
                        candidates=guesses,
                        pose=pose,
                    )
                )
        return matches

    def _learn(self, name: str, feature: Any, pose: tuple[float, float]) -> bool:
        """One more photo of *name* from an angle it lacks (rate-limited)."""
        now = _book.time.time()
        stamps = [t for t in self._learnt.get(name, []) if now - t < 86400]
        if (stamps and now - stamps[-1] < _book.LEARN_GAP) or len(
            stamps
        ) >= _book.LEARN_DAILY:
            return False
        angle = _book.angle_of(pose)
        with self._lock:
            try:
                people = self._load(strict=True)
            except _book.FaceError:
                return False
            person = people.get(name)
            if not person:
                return False
            count = len(person["embeddings"])
            poses = _book._column(person, "poses", count)
            if (
                sum(1 for x in poses if x and _book.angle_of(x) == angle)
                >= _book.LEARN_PER_ANGLE
            ):
                return False
            _book._add_samples(person, [(feature.tolist(), None, pose, "auto")])
            self._save(people)
        self._learnt[name] = stamps + [now]
        return True


__all__ = [
    "_IdentifyMixin",
]
