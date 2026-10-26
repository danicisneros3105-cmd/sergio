"""The live eye: instant looks, change detection, checks as soon as it shows."""

from __future__ import annotations

import base64
import io
import threading
import time

from PIL import Image
from sergio_escritorio.control import Controller
from sergio_escritorio.live_screen import LiveScreen, changed_box, signature


def picture(colour=(255, 255, 255), box=None, size=(1600, 900)):
    img = Image.new("RGB", size, colour)
    if box:
        img.paste((0, 0, 0), box)
    return img


class Screen:
    def __init__(self):
        self.image = picture()
        self.grabs = 0

    def grab(self):
        self.grabs += 1
        return self.image.copy()


def test_changes_are_found_and_boxed():
    a, b = picture(), picture(box=(800, 400, 1000, 500))
    box = changed_box(signature(a), signature(b), a.size)
    assert (
        box is not None
        and box[0] <= 800
        and box[2] >= 1000
        and box[1] <= 400
        and box[3] >= 500
    )
    assert changed_box(signature(a), signature(picture()), a.size) is None


def test_same_picture_keeps_the_frame_and_its_encoding():
    screen = Screen()
    eye = LiveScreen(screen.grab)
    first = eye.capture()
    jpeg = first.encode("JPEG", 1280)
    again = eye.capture()
    assert again is first and again.encode("JPEG", 1280) is jpeg  # encoded once
    assert eye.cache_hits == 1
    screen.image = picture(box=(0, 0, 400, 400))
    assert eye.capture().id == first.id + 1


def test_capture_deadlines_keep_fractional_target_and_report_observed_fps():
    from sergio_escritorio.live_screen import FAST_FPS

    now = [0.0]
    frames = []
    image = picture(size=(64, 36))

    def grab():
        frames.append(now[0])
        now[0] += 0.007  # simulated capture takes 7 ms, not a zero-cost stub
        return image

    def sleep(delay):
        now[0] += delay
        if len(frames) >= 200:
            eye._running = False

    eye = LiveScreen(grab, clock=lambda: now[0], sleep=sleep)
    eye.streaming = eye._running = True
    eye.need(1e9)  # Sergio is acting on the screen: full speed
    eye._loop()
    assert abs((frames[-1] - frames[0]) - 199 / FAST_FPS) < 1e-9
    assert abs(eye.capture_fps - FAST_FPS) < 1e-9
    assert eye.cache_hits == 199


def test_watcher_wakes_up_on_the_change():
    screen = Screen()
    eye = LiveScreen(screen.grab).start()
    try:
        start = eye.latest().id
        threading.Timer(
            0.15, lambda: setattr(screen, "image", picture(box=(100, 100, 600, 600)))
        ).start()
        t0 = time.monotonic()
        frame = eye.wait_change(start, 2.0)
        took = time.monotonic() - t0
        assert frame is not None and frame.id > start
        assert took < 0.6  # seen within a couple of frames, not after a fixed wait
        assert eye.wait_change(frame.id, 0.2) is None  # nothing else moved
    finally:
        eye.stop()


class Backend:
    def __init__(self, screen):
        self.screen = screen
        self.title = "Bloc de notas"
        self.ui_reads = 0

    def screenshot(self):
        return self.screen.grab()

    def ui(self):
        self.ui_reads += 1
        return {
            "window": self.title,
            "windows": [self.title],
            "elements": [
                {"name": "Guardar", "type": "button", "rect": (10, 10, 50, 30)}
            ],
        }

    def active_window(self):
        return self.title

    def click(self, x, y, button, clicks):
        self.screen.image = picture(box=(0, 0, 800, 800))


def test_controller_looks_through_the_live_eye():
    screen = Screen()
    backend = Backend(screen)
    eye = LiveScreen(backend.screenshot)
    ctl = Controller(backend, sleep=lambda s: None, strict_permissions=False, live=eye)
    shot = ctl.screen("jpeg")
    img = Image.open(io.BytesIO(base64.b64decode(shot["image_jpeg_b64"])))
    assert img.format == "JPEG" and img.width == 1280 and shot["frame"] == 1
    assert ctl.screen()["image_png_b64"]  # the old PNG answer still works
    ctl.ui()
    ctl.ui()
    assert backend.ui_reads == 1  # same frame: the tree is not read again
    out = ctl.act({"action": "click", "x": 20, "y": 20})
    assert "the screen changed" in out and "Bloc de notas" in out
    ctl.ui()
    assert backend.ui_reads == 2  # new frame: read again
    png, elements, scale = ctl.snapshot("jpeg")
    assert png[:2] == b"\xff\xd8" and elements and scale == 1600 / 1280


def test_the_live_video_shows_the_mouse_pointer():
    from sergio_escritorio.live_screen import with_cursor

    screen = Screen()
    live = LiveScreen(screen.grab)
    frame = live.capture()
    plain = with_cursor(frame, None)
    assert plain == frame.encode("JPEG", 1280, 80)
    marked = with_cursor(frame, (800, 450))
    assert marked != plain
    centre = Image.open(io.BytesIO(marked)).convert("RGB").getpixel((640, 360))
    assert centre[0] > 200 and centre[1] > 160 and centre[2] < 100  # yellow
    assert with_cursor(frame, (800, 450)) is marked  # cached
    with_cursor(frame, (100, 100))
    assert sum(1 for k in frame._encoded if k[0] == "cursor") == 1  # only the latest
    assert with_cursor(frame, (5000, 5000)) == plain  # off this monitor


def test_the_glow_breathes_and_rises_with_his_voice():
    from sergio_escritorio.screen_glow import intensity

    quiet = [intensity(t / 10, 0.0, False) for t in range(60)]
    assert 0.35 < min(quiet) < max(quiet) < 0.75
    assert intensity(0.0, 0.8, True) > intensity(0.0, 0.8, False)
    assert intensity(0.0, 1.0, True) <= 1.0


def test_the_eye_is_calm_unless_someone_looks():
    # Owner, 26 Oct 2026: «realentiza mi laptop». Nobody looking: one glance a
    # second, even while a video plays; a call sharing the screen: 8; Sergio
    # looking or acting: the full rate, at once.
    from sergio_escritorio.live_screen import CALM_FPS, FAST_FPS, SHARE_FPS

    now = [0.0]
    frames: list[float] = []
    n = [0]

    def grab():
        frames.append(now[0])
        n[0] += 1
        return picture(size=(64, 36), box=(0, 0, 8 + n[0] % 50, 8))  # always moving

    def rate(setup) -> float:
        frames.clear()
        eye = LiveScreen(grab, clock=lambda: now[0], sleep=sleep)
        eye._running = True
        setup(eye)

        def stop_after_forty():
            if len(frames) >= 40:
                eye._running = False

        sleep.after = stop_after_forty
        eye._loop()
        return (len(frames) - 1) / (frames[-1] - frames[0])

    def sleep(delay):
        now[0] += delay
        sleep.after()

    assert abs(rate(lambda e: None) - CALM_FPS) < 0.05
    assert abs(rate(lambda e: setattr(e, "streaming", True)) - SHARE_FPS) < 0.2
    assert abs(rate(lambda e: e.need(1e9)) - FAST_FPS) < 0.5
    eye = LiveScreen(grab, clock=lambda: now[0], sleep=sleep)
    assert not eye.watched
    eye.latest(look=False)
    assert not eye.watched  # the call's own sampling is not a look
    eye.latest()
    assert eye.watched
