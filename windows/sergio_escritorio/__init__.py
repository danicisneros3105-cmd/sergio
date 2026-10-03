"""Sergio Escritorio: the part of Sergio that lives directly in Windows.

Sergio's brain runs in WSL (Ubuntu), which cannot see or touch the Windows
desktop. This small app runs in Windows and gives Sergio:

* its own window (no browser tabs), a tray icon and a global hotkey;
* push-to-talk voice (Ctrl+Alt+Space) answered out loud;
* a local, token-protected control server so Sergio can read the screen and
  use the mouse and keyboard like the user would, with a hard stop hotkey
  (Ctrl+Alt+End) and pyautogui's corner fail-safe.
"""

__version__ = "0.1.0"
