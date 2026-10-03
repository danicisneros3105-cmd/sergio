"""Sergio Escritorio: the part of Sergio that lives directly in Windows.

Sergio's brain runs in WSL (Ubuntu), which cannot see or touch the Windows
desktop. This small program runs in Windows, with no app window:

* a cursor companion (a small orb next to the mouse pointer) that shows what
  Sergio hears, thinks, says and does;
* voice: say "Sergio, ..." or press Ctrl+Space, and Sergio answers aloud;
* a local, token-protected control server so Sergio can read the screen and
  use the mouse and keyboard like the user would, with a hard stop hotkey
  (Ctrl+Alt+End) and pyautogui's corner fail-safe.
"""

__version__ = "0.2.0"
