"""Live screen: Sergio's eye on the screen you are using, always open.

Before, every look took a fresh screenshot (new capture context, resize, PNG)
and read the accessibility tree on the spot: 150–600 ms before Sergio could
even start thinking, and actions were checked with fixed waits.

Now one background thread watches the screen continuously at the configured
frame rate while something moves or screen sharing is active (4 when it is
still and nobody watches), with a persistent capture context, and keeps:

* the latest frame, its id and *what* changed (the changed box),
* the frame already encoded (JPEG and PNG) — encoded once per frame, so
  any number of looks cost nothing while the screen does not change,
* change notifications: ``wait_change`` wakes up the moment the screen
  changes after an action, ``wait_settled`` when it has stopped changing —
  so control is checked as soon as the result is visible, never later,
* an MJPEG stream (``/screen/stream``) for a live view.

Nothing leaves the PC from here: frames are only served to the local
control server (token-protected) and to the call when screen sharing is on.
"""

from __future__ import annotations

import io
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

SIG_W, SIG_H = 64, 36  # the tiny grey picture changes are measured on
CHANGE = 6  # mean grey difference of a cell that counts as a change
try:  # Local target; provider delivery must be measured separately.
    FAST_FPS = float(os.environ.get("SERGIO_LIVE_FPS", "32.310520139305"))
    if not math.isfinite(FAST_FPS) or not 1 <= FAST_FPS <= 60:
        raise ValueError("Invalid frame rate")
except ValueError:
    FAST_FPS = 32.310520139305
IDLE_FPS = 4.0
IDLE_AFTER = 3.0  # seconds without changes before slowing down


@dataclass
class Frame:
    id: int
    image: Any  # PIL.Image
    at: float  # monotonic time it was captured
    origin: tuple[int, int] = (0, 0)
    changed: Optional[tuple[int, int, int, int]] = None  # box in image pixels
    _encoded: dict = field(default_factory=dict, repr=False)

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size

    def small(self, width: int) -> Any:
        """The frame at most *width* wide, in RGB (cached). Big screens are
        first halved with a box filter, which costs a few milliseconds where
        a full-size resize costs tens — what keeps 32 frames a second."""
        key = ("small", width)
        hit = self._encoded.get(key)
        if hit is not None:
            return hit
        image = self.image
        if image.mode != "RGB":
            image = image.convert("RGB")
        if image.width > width:
            # Halve (or quarter) with a box filter when that lands near the
            # size asked: 1920 → 960, 3840 → 960. Far cheaper than a resize.
            factor = max(1, round(image.width / width))
            if factor >= 2:
                image = image.reduce(factor)
            if image.width > width * 1.3:
                from PIL import Image

                image = image.resize(
                    (width, round(image.height * width / image.width)), Image.BILINEAR
                )
        self._encoded[key] = image
        return image

    def encode(self, fmt: str = "JPEG", width: int = 1280, quality: int = 78) -> bytes:
        """The frame as JPEG or PNG at most *width* wide (cached)."""
        key = (fmt, width, quality)
        hit = self._encoded.get(key)
        if hit is not None:
            return hit
        image = self.image
        if image.width > width:
            from PIL import Image

            image = image.resize(
                (width, round(image.height * width / image.width)), Image.BILINEAR
            )
        buf = io.BytesIO()
        if fmt == "PNG":
            image.convert("RGB").save(buf, format="PNG", compress_level=1)
        else:
            image.convert("RGB").save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        self._encoded[key] = data
        return data


def with_cursor(
    frame: "Frame",
    cursor: Optional[tuple[int, int]],
    width: int = 1280,
    quality: int = 80,
) -> bytes:
    """The frame as Gemini sees it live: a JPEG with the mouse pointer drawn
    in (screenshots do not include it), so he knows where you are pointing."""
    if cursor is None:
        return frame.encode("JPEG", width, quality)
    x, y = cursor[0] - frame.origin[0], cursor[1] - frame.origin[1]
    w, h = frame.size
    if not (0 <= x < w and 0 <= y < h):
        return frame.encode("JPEG", width, quality)
    key = ("cursor", x // 2, y // 2, width, quality)
    hit = frame._encoded.get(key)
    if hit is not None:
        return hit
    from PIL import Image, ImageDraw

    image = frame.image.convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    r = max(10, w // 110)  # stays visible after the resize to 1280
    draw.ellipse((x - r, y - r, x + r, y + r), outline=(0, 0, 0), width=max(3, r // 3))
    draw.ellipse(
        (x - r + 2, y - r + 2, x + r - 2, y + r - 2),
        outline=(255, 214, 10),
        width=max(2, r // 4),
    )
    draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 214, 10))
    if image.width > width:
        image = image.resize(
            (width, round(image.height * width / image.width)), Image.BILINEAR
        )
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    data = buf.getvalue()
    for old in [k for k in frame._encoded if k[0] == "cursor"]:
        del frame._encoded[old]  # only the latest pointer position is kept
    frame._encoded[key] = data
    return data


def video_jpeg(
    frame: "Frame",
    cursor: Optional[tuple[int, int]],
    width: int = 1024,
    quality: int = 62,
) -> bytes:
    """One frame of the live video for Gemini, fast: shrink first, then draw
    the pointer on the small picture and encode. Cached per frame, pointer
    spot and size, so a still screen costs nothing to send again."""
    pos = None
    if cursor is not None:
        x, y = cursor[0] - frame.origin[0], cursor[1] - frame.origin[1]
        w, h = frame.size
        if 0 <= x < w and 0 <= y < h:
            pos = (x, y)
    key = ("video", width, quality, (pos[0] // 4, pos[1] // 4) if pos else None)
    hit = frame._encoded.get(key)
    if hit is not None:
        return hit
    image = frame.small(width)
    if pos is not None:
        from PIL import ImageDraw

        image = image.copy()
        scale = image.width / frame.size[0]
        x, y = pos[0] * scale, pos[1] * scale
        r = max(6, image.width // 110)
        draw = ImageDraw.Draw(image)
        draw.ellipse(
            (x - r, y - r, x + r, y + r), outline=(0, 0, 0), width=max(2, r // 3)
        )
        draw.ellipse(
            (x - r + 2, y - r + 2, x + r - 2, y + r - 2),
            outline=(255, 214, 10),
            width=max(2, r // 4),
        )
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 214, 10))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    data = buf.getvalue()
    for old in [
        k for k in frame._encoded if k[0] == "video" and k[1:3] == (width, quality)
    ]:
        del frame._encoded[old]  # only the latest pointer spot is kept
    frame._encoded[key] = data
    return data


def signature(image: Any) -> bytes:
    """A 64×36 grey thumbnail: enough to see a click's effect, cheap to compare."""
    from PIL import Image

    # Shrink before turning grey: converting a 4K frame first costs ~10 ms.
    small = (
        image.reduce(max(1, image.width // (SIG_W * 8)))
        if image.width > SIG_W * 16
        else image
    )
    return small.convert("L").resize((SIG_W, SIG_H), Image.BOX).tobytes()


def changed_box(
    before: bytes, after: bytes, size: tuple[int, int]
) -> Optional[tuple[int, int, int, int]]:
    """The box (in image pixels) around the cells that changed, or None."""
    if len(before) != len(after):
        return (0, 0, size[0], size[1])
    xs: list[int] = []
    ys: list[int] = []
    for i in range(len(after)):
        if abs(after[i] - before[i]) > CHANGE:
            xs.append(i % SIG_W)
            ys.append(i // SIG_W)
    if not xs:
        return None
    cw, ch = size[0] / SIG_W, size[1] / SIG_H
    return (
        int(min(xs) * cw),
        int(min(ys) * ch),
        int((max(xs) + 1) * cw),
        int((max(ys) + 1) * ch),
    )


class LiveScreen:
    """Watches the screen in the background; every look is instant."""

    def __init__(
        self,
        grab: Callable[[], Any],
        origin: Callable[[], tuple[int, int]] = lambda: (0, 0),
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._grab = grab
        self._origin = origin
        self._clock = clock
        self._sleep = sleep
        self._cond = threading.Condition()
        self._frame: Optional[Frame] = None
        self._sig: bytes = b""
        self._last_change = 0.0
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.paused = False  # e.g. while the screen is locked
        # While Gemini watches it live the eye never slows down to idle.
        self.streaming = False
        self.capture_ms = 0.0  # how long the last grab took (for the stats)
        self.capture_fps = 0.0  # observed captures, including unchanged images
        self.cache_hits = 0  # identical images reuse the frame and encodings
        self._capture_times: deque[float] = deque(maxlen=256)
        self.on_change: Callable[[Frame], None] = lambda _f: None

    # -- the eye --------------------------------------------------------------
    def capture(self) -> Frame:
        """Take one frame now (also used when the watcher is not running)."""
        image = self._grab()
        sig = signature(image)
        now = self._clock()
        with self._cond:
            self._capture_times.append(now)
            while self._capture_times and now - self._capture_times[0] > 2.0:
                self._capture_times.popleft()
            if len(self._capture_times) > 1:
                span = now - self._capture_times[0]
                self.capture_fps = (
                    (len(self._capture_times) - 1) / span if span > 0 else 0.0
                )
            prev = self._frame
            box = (
                changed_box(self._sig, sig, image.size) if prev else (0, 0, *image.size)
            )
            if prev is not None and box is None:
                self.cache_hits += 1
                # same picture: keep the old frame (and its encodings), fresher
                prev.at = now
                return prev
            frame = Frame(
                id=(prev.id + 1) if prev else 1,
                image=image,
                at=now,
                origin=self._origin(),
                changed=box,
            )
            self._frame, self._sig, self._last_change = frame, sig, now
            self._cond.notify_all()
        try:
            self.on_change(frame)
        except Exception:  # noqa: BLE001 — a listener never stops the eye
            pass
        return frame

    def _loop(self) -> None:
        # A fixed beat (next += period), not «sleep the rest»: rounding and
        # slow grabs do not accumulate drift. The OS/hardware can still miss
        # deadlines: capture_fps reports observations rather than the target.
        due = self._clock()
        while self._running:
            started = self._clock()
            if not self.paused:
                try:
                    self.capture()
                except Exception:  # noqa: BLE001 — e.g. secure desktop: try again
                    self._sleep(0.5)
                    due = self._clock()
                    continue
                self.capture_ms = (self._clock() - started) * 1000
            idle = not self.streaming and started - self._last_change > IDLE_AFTER
            period = 1.0 / (IDLE_FPS if idle else FAST_FPS)
            due += period
            now = self._clock()
            if now - due > period:  # fell behind (a slow grab): start a new beat
                due = now
            self._sleep(max(0.0, due - now))

    def start(self) -> "LiveScreen":
        if self._thread is None or not self._thread.is_alive():
            self._running = True
            self._thread = threading.Thread(
                target=self._loop, name="live-screen", daemon=True
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return bool(self._running and self._thread and self._thread.is_alive())

    # -- looking -----------------------------------------------------------------
    def latest(self, max_age: float = 0.25) -> Frame:
        """The current frame; captured now only if the eye is not watching."""
        with self._cond:
            frame = self._frame
        if frame is None or (not self.running and self._clock() - frame.at > max_age):
            return self.capture()
        return frame

    def wait_change(self, after: int, timeout: float) -> Optional[Frame]:
        """The first frame newer than *after*, or None if nothing changed."""
        end = self._clock() + timeout
        with self._cond:
            while True:
                if self._frame is not None and self._frame.id > after:
                    return self._frame
                left = end - self._clock()
                if left <= 0:
                    return None
                if not self.running:
                    break
                self._cond.wait(min(left, 0.05))
        # not watching: look by ourselves until the timeout
        while self._clock() < end:
            frame = self.capture()
            if frame.id > after:
                return frame
            self._sleep(1.0 / FAST_FPS)
        return None

    def wait_settled(self, quiet: float = 0.12, timeout: float = 1.5) -> Frame:
        """The frame once the screen stopped changing for *quiet* seconds."""
        end = self._clock() + timeout
        frame = self.latest()
        while self._clock() < end:
            newer = self.wait_change(
                frame.id, min(quiet, max(0.0, end - self._clock()))
            )
            if newer is None:
                return frame
            frame = newer
        return frame

    def stream(self, fps: float = 8.0, width: int = 1280) -> Iterator[bytes]:
        """MJPEG parts: one per new frame (at most *fps* a second)."""
        last = 0
        while True:
            frame = self.wait_change(last, 2.0) or self.latest()
            last = frame.id
            jpeg = frame.encode("JPEG", width)
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode()
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
            self._sleep(1.0 / fps)


__all__ = [
    "Frame",
    "LiveScreen",
    "changed_box",
    "signature",
    "video_jpeg",
    "with_cursor",
]
