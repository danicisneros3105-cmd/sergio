"""Modo Stark: crea figuras con las manos y mueve cosas en pantalla.

Gestos (una o dos manos frente a la cámara):

- **Pinza** (pulgar + índice juntos): agarrar una figura y arrastrarla.
  En modo pantalla, equivale a mantener el botón izquierdo del ratón.
- **Pinza larga** (0,8 s en el vacío): crear una figura donde está la mano.
- **Pinza con las dos manos** sobre una figura: escalar y girar (como
  "pellizcar para hacer zoom").
- **Palma abierta en movimiento**: empujar figuras.
- **Puño**: soltar todo lo agarrado.
- **Índice extendido**: en modo pantalla, el ratón sigue al dedo.

Teclas: ``C`` cambia el tipo de figura, ``X`` borra la última,
``T`` activa/desactiva el control del escritorio, ``Q`` sale.
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass, field

PINCH_DIST = 0.055  # normalized thumb-tip ↔ index-tip distance
LONG_PINCH_SECONDS = 0.8  # hold to create a shape
PALM_PUSH_SPEED = 1.6  # normalized units/s for an open-palm push
SHAPE_KINDS = ("cubo", "esfera", "piramide", "anillo")
SHAPE_COLORS = {
    "cubo": (0, 200, 255),
    "esfera": (255, 120, 0),
    "piramide": (0, 255, 160),
    "anillo": (200, 0, 255),
}


@dataclass
class Hand:
    """Landmark summary of one detected hand."""

    landmarks: list[tuple[float, float]]  # 21 normalized (x, y) points
    pinch: float  # thumb↔index distance
    index_tip: tuple[float, float]
    center: tuple[float, float]

    @property
    def is_pinch(self) -> bool:
        return self.pinch < PINCH_DIST

    @property
    def is_open_palm(self) -> bool:
        # fingertips (8,12,16,20) farther from wrist (0) than knuckles (5,9,13,17)
        wrist = self.landmarks[0]
        tips = sum(
            _dist(self.landmarks[i], wrist) for i in (8, 12, 16, 20)
        )
        bases = sum(
            _dist(self.landmarks[i], wrist) for i in (5, 9, 13, 17)
        )
        return tips > bases * 1.15

    @property
    def is_fist(self) -> bool:
        wrist = self.landmarks[0]
        tips = sum(
            _dist(self.landmarks[i], wrist) for i in (8, 12, 16, 20)
        )
        bases = sum(
            _dist(self.landmarks[i], wrist) for i in (5, 9, 13, 17)
        )
        return tips < bases * 0.9


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class Shape:
    """A figure floating in the air canvas."""

    kind: str
    x: float  # normalized 0-1
    y: float
    size: float = 0.08
    angle: float = 0.0
    vx: float = 0.0  # push velocity
    vy: float = 0.0
    grabbed: bool = False

    def contains(self, x: float, y: float) -> bool:
        return _dist((self.x, self.y), (x, y)) <= self.size

    def step(self, dt: float) -> None:
        self.x = min(1.0, max(0.0, self.x + self.vx * dt))
        self.y = min(1.0, max(0.0, self.y + self.vy * dt))
        self.vx *= 0.92  # friction
        self.vy *= 0.92

    def draw(self, frame: object, width: int, height: int) -> None:
        import cv2

        cx, cy = int(self.x * width), int(self.y * height)
        r = max(8, int(self.size * min(width, height)))
        color = SHAPE_COLORS.get(self.kind, (255, 255, 255))
        if self.kind == "esfera":
            cv2.circle(frame, (cx, cy), r, color, 3)
            cv2.circle(frame, (cx, cy), r // 2, color, 1)
        elif self.kind == "cubo":
            pts = _rotated_square(cx, cy, r, self.angle)
            cv2.polylines(frame, [pts], True, color, 3)
        elif self.kind == "piramide":
            pts = _rotated_triangle(cx, cy, r, self.angle)
            cv2.polylines(frame, [pts], True, color, 3)
        else:  # anillo
            cv2.ellipse(
                frame, (cx, cy), (r, int(r * 0.45)), self.angle * 57.3, 0, 360,
                color, 3,
            )


def _rotated_square(cx: int, cy: int, r: int, angle: float):
    import numpy as np

    return np.array(
        [
            (
                int(cx + r * math.cos(angle + math.pi / 4 + i * math.pi / 2)),
                int(cy + r * math.sin(angle + math.pi / 4 + i * math.pi / 2)),
            )
            for i in range(4)
        ]
    )


def _rotated_triangle(cx: int, cy: int, r: int, angle: float):
    import numpy as np

    return np.array(
        [
            (
                int(cx + r * math.cos(angle - math.pi / 2 + i * 2 * math.pi / 3)),
                int(cy + r * math.sin(angle - math.pi / 2 + i * 2 * math.pi / 3)),
            )
            for i in range(3)
        ]
    )


class StarkApp:
    """Webcam hand-tracking air canvas with optional desktop control."""

    def __init__(self, camera: int = 0, control_screen: bool = False) -> None:
        self.camera = camera
        self.control_screen = control_screen
        self.shapes: list[Shape] = []
        self.shape_index = 0
        self._pinch_since: float | None = None
        self._two_hand_anchor: tuple[float, float] | None = None
        self._prev_centers: dict[int, tuple[float, float]] = {}
        self._mouse_down = False
        self._screen_size: tuple[int, int] | None = None

    # -- desktop control ----------------------------------------------------

    def _mouse(self):
        try:
            import pyautogui

            pyautogui.FAILSAFE = True  # slam the mouse to a corner to abort
            return pyautogui
        except ImportError:
            return None

    def _move_mouse(self, x: float, y: float) -> None:
        gui = self._mouse()
        if gui is None:
            return
        if self._screen_size is None:
            self._screen_size = gui.size()
        w, h = self._screen_size
        # mirror X like the preview; smooth a touch
        gui.moveTo(int((1 - x) * w), int(y * h), duration=0.02)

    def _mouse_drag(self, pinching: bool) -> None:
        gui = self._mouse()
        if gui is None:
            return
        if pinching and not self._mouse_down:
            gui.mouseDown()
            self._mouse_down = True
        elif not pinching and self._mouse_down:
            gui.mouseUp()
            self._mouse_down = False

    # -- gesture handling -----------------------------------------------------

    def _grab_or_create(self, hand: Hand, now: float) -> None:
        target = self._shape_at(hand.index_tip)
        if target is not None:
            target.grabbed = True
            target.x, target.y = hand.index_tip
            target.vx = target.vy = 0.0
            self._pinch_since = None
        else:
            if self._pinch_since is None:
                self._pinch_since = now
            elif now - self._pinch_since >= LONG_PINCH_SECONDS:
                kind = SHAPE_KINDS[self.shape_index % len(SHAPE_KINDS)]
                self.shapes.append(Shape(kind, *hand.index_tip))
                self._pinch_since = None

    def _shape_at(self, point: tuple[float, float]) -> Shape | None:
        for shape in reversed(self.shapes):  # top-most first
            if shape.contains(*point):
                return shape
        return None

    def _two_hand_transform(self, a: Hand, b: Hand) -> None:
        d = _dist(a.index_tip, b.index_tip)
        angle = math.atan2(
            b.index_tip[1] - a.index_tip[1], b.index_tip[0] - a.index_tip[0]
        )
        if self._two_hand_anchor is None:
            self._two_hand_anchor = (d, angle)
            return
        d0, angle0 = self._two_hand_anchor
        mid = (
            (a.index_tip[0] + b.index_tip[0]) / 2,
            (a.index_tip[1] + b.index_tip[1]) / 2,
        )
        shape = self._shape_at(mid) or (self.shapes[-1] if self.shapes else None)
        if shape is not None and d0 > 1e-6:
            shape.size = min(0.3, max(0.02, shape.size * (d / d0)))
            shape.angle += angle - angle0
        self._two_hand_anchor = (d, angle)

    def _push_with_palm(self, hand: Hand, hand_id: int, dt: float) -> None:
        prev = self._prev_centers.get(hand_id)
        self._prev_centers[hand_id] = hand.center
        if prev is None or dt <= 0:
            return
        vx, vy = (hand.center[0] - prev[0]) / dt, (hand.center[1] - prev[1]) / dt
        speed = math.hypot(vx, vy)
        if speed < PALM_PUSH_SPEED:
            return
        for shape in self.shapes:
            if shape.contains(*hand.center):
                shape.vx, shape.vy = vx, vy

    # -- main loop -------------------------------------------------------------

    def run(self) -> int:
        try:
            import cv2
            import mediapipe as mp
        except ImportError:
            print(
                "Faltan dependencias. Instala con:\n"
                "  uv sync --extra gestures\n"
                "y para mover el ratón/ventanas: --extra screen-control"
            )
            return 1

        cap = cv2.VideoCapture(self.camera)
        if not cap.isOpened():
            print("No se pudo abrir la cámara.")
            return 1

        hands_mp = mp.solutions.hands.Hands(
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.6,
        )
        last = time.monotonic()
        print("Modo Stark activo. Q para salir, C cambia figura, T pantalla.")
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame = cv2.flip(frame, 1)  # espejo, como un holograma
                height, width = frame.shape[:2]
                now = time.monotonic()
                dt = now - last
                last = now

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands_mp.process(rgb)
                hands = _extract_hands(result)

                if hands:
                    any_pinch = any(h.is_pinch for h in hands)
                    if len(hands) == 2 and all(h.is_pinch for h in hands):
                        self._two_hand_transform(hands[0], hands[1])
                    else:
                        self._two_hand_anchor = None
                        for i, hand in enumerate(hands):
                            if hand.is_fist:
                                for shape in self.shapes:
                                    shape.grabbed = False
                                self._pinch_since = None
                                if self.control_screen:
                                    self._mouse_drag(False)
                            elif hand.is_pinch:
                                self._grab_or_create(hand, now)
                                if self.control_screen:
                                    self._move_mouse(*hand.index_tip)
                                    self._mouse_drag(True)
                            else:
                                self._pinch_since = None
                                self._push_with_palm(hand, i, dt)
                                if self.control_screen:
                                    self._move_mouse(*hand.index_tip)
                                    self._mouse_drag(False)
                    if not any_pinch and self.control_screen:
                        self._mouse_drag(False)
                else:
                    self._pinch_since = None
                    self._two_hand_anchor = None
                    if self.control_screen:
                        self._mouse_drag(False)

                for shape in self.shapes:
                    if not shape.grabbed:
                        shape.step(dt)
                    shape.grabbed = False
                    shape.draw(frame, width, height)

                _draw_hud(frame, self, width)
                cv2.imshow("Sergio — Modo Stark", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("c"):
                    self.shape_index += 1
                elif key == ord("x") and self.shapes:
                    self.shapes.pop()
                elif key == ord("t"):
                    self.control_screen = not self.control_screen
        finally:
            if self._mouse_down:
                self._mouse_drag(False)
            hands_mp.close()
            cap.release()
            cv2.destroyAllWindows()
        return 0


def _extract_hands(result: object) -> list[Hand]:
    hands: list[Hand] = []
    for lm_list in getattr(result, "multi_hand_landmarks", None) or []:
        points = [(lm.x, lm.y) for lm in lm_list.landmark]
        if len(points) < 21:
            continue
        center = (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
        hands.append(
            Hand(
                landmarks=points,
                pinch=_dist(points[4], points[8]),
                index_tip=points[8],
                center=center,
            )
        )
    return hands


def _draw_hud(frame: object, app: StarkApp, width: int) -> None:
    import cv2

    kind = SHAPE_KINDS[app.shape_index % len(SHAPE_KINDS)]
    lines = [
        f"Figura: {kind} (C cambia, X borra)",
        f"Control pantalla: {'SI' if app.control_screen else 'NO'} (T)",
        f"Figuras: {len(app.shapes)}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(
            frame, line, (10, 24 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
            (0, 255, 255), 1, cv2.LINE_AA,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sergio gestos")
    parser.add_argument("--camara", type=int, default=0, help="índice de cámara")
    parser.add_argument(
        "--pantalla",
        action="store_true",
        help="también controla el ratón y las ventanas del escritorio",
    )
    args = parser.parse_args(argv)
    return StarkApp(camera=args.camara, control_screen=args.pantalla).run()


if __name__ == "__main__":
    raise SystemExit(main())
