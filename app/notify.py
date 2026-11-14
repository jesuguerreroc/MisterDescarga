"""Avisos de Windows al terminar una descarga.

Usa un icono en la bandeja (NotifyIcon de WinForms, que pywebview ya carga). Windows
10/11 muestra su globo como notificación normal. No hace falta registrar nada en el
sistema, así la app sigue siendo portátil.
"""

import ctypes
from pathlib import Path

from version import APP_NAME


class Notifier:
    def __init__(self, window, icon: Path | None):
        self._window = window
        self._icon = icon
        self._tray = None
        self._hwnd = 0
        self._click_path = ""

    def set_hwnd(self, hwnd: int) -> None:
        self._hwnd = hwnd

    def window_active(self) -> bool:
        """¿La ventana está al frente? Entonces el aviso sobra: ya se ve en la lista."""
        if not self._hwnd:
            return False
        user32 = ctypes.windll.user32
        return user32.GetForegroundWindow() == self._hwnd and not user32.IsIconic(self._hwnd)

    def show(self, title: str, text: str, path: str = "") -> None:
        def on_ui():
            from System.Windows.Forms import ToolTipIcon  # type: ignore[import-not-found]

            tray = self._ensure_tray()
            self._click_path = path
            tray.BalloonTipTitle = title[:63]
            tray.BalloonTipText = text[:250] or " "
            tray.BalloonTipIcon = getattr(ToolTipIcon, "None")
            tray.ShowBalloonTip(6000)

        self._invoke(on_ui)

    def dispose(self) -> None:
        def on_ui():
            if self._tray is not None:
                self._tray.Visible = False
                self._tray.Dispose()
                self._tray = None

        self._invoke(on_ui)

    # ---------- internos ----------
    def _invoke(self, fn) -> None:
        try:
            from System import Action  # type: ignore[import-not-found]

            form = self._window.native
            if form is None:
                return
            form.Invoke(Action(fn))
        except Exception:
            pass

    def _ensure_tray(self):
        if self._tray is not None:
            return self._tray
        from System.Drawing import Icon, SystemIcons  # type: ignore[import-not-found]
        from System.Windows.Forms import NotifyIcon  # type: ignore[import-not-found]

        tray = NotifyIcon()
        tray.Icon = Icon(str(self._icon)) if self._icon else SystemIcons.Application
        tray.Text = APP_NAME
        tray.BalloonTipClicked += self._on_balloon_click
        tray.MouseClick += self._on_tray_click
        tray.Visible = True
        self._tray = tray
        return tray

    def _on_balloon_click(self, _sender, _args) -> None:
        if self._click_path:
            from downloader import open_in_explorer

            try:
                open_in_explorer(self._click_path, select=Path(self._click_path).is_file())
                return
            except OSError:
                pass
        self._bring_to_front()

    def _on_tray_click(self, _sender, _args) -> None:
        self._bring_to_front()

    def _bring_to_front(self) -> None:
        try:
            from System.Windows.Forms import FormWindowState  # type: ignore[import-not-found]

            form = self._window.native
            if form.WindowState == FormWindowState.Minimized:
                form.WindowState = FormWindowState.Normal
            form.Activate()
        except Exception:
            pass
