"""MisterDescarga: punto de entrada. Abre la ventana con la interfaz."""

import os
import sys
from pathlib import Path

import webview

import settings
import taskbar
import window_theme
from api import Api
from notify import Notifier
from paths import APP_ROOT
from version import APP_NAME


def ui_entry() -> str:
    """Ruta a la interfaz compilada (o el servidor de Vite si MD_DEV=1)."""
    if os.environ.get("MD_DEV") == "1":
        return "http://localhost:5173"
    here = Path(__file__).resolve().parent.parent
    for base in (here / "ui", here / "ui" / "dist"):  # versión portátil / código fuente
        if (base / "index.html").exists():
            return str(base / "index.html")
    sys.exit("No se encontró la interfaz. Ejecuta `npm run build` dentro de ui/.")


def find_icon() -> Path | None:
    here = Path(__file__).resolve().parent.parent
    for p in (
        here / "icon.ico",  # versión portátil (sistema/icon.ico)
        here / "assets" / "icon.ico",  # código fuente
    ):
        if p.exists():
            return p
    return None


def relaunch_command() -> str:
    """Lo que ejecuta Windows al abrir MisterDescarga desde la barra de tareas."""
    exe = Path(sys.executable).resolve()
    if (APP_ROOT / "sistema" / "portable.txt").exists():
        return f'"{exe}"'
    return f'"{exe}" "{Path(__file__).resolve()}"'  # desde el código fuente


def setup_native_window(window, api: Api, icon: Path | None, dark: bool) -> None:
    """Pingüino en la ventana y la barra de tareas (aunque el .exe sea pythonw) y
    barra de título del color del tema."""
    try:
        from System import Action  # type: ignore[import-not-found]
        from System.Drawing import Icon  # type: ignore[import-not-found]

        form = window.native

        def on_ui_thread():
            hwnd = int(form.Handle.ToInt64())
            api._set_hwnd(hwnd)
            window_theme.apply_titlebar(hwnd, dark)
            if icon:
                form.Icon = Icon(str(icon))
                taskbar.set_window_identity(hwnd, relaunch_command(), f"{icon},0", APP_NAME)

        form.Invoke(Action(on_ui_thread))
    except Exception:
        pass


def quiet_windows_errors() -> None:
    """Evita las ventanas de Windows tipo "Imagen incorrecta" si una herramienta no
    puede cargar (p. ej. bloqueada por Smart App Control). La app detecta el fallo
    por su cuenta y lo explica en Ajustes. Los procesos hijos heredan este modo."""
    try:
        import ctypes

        SEM_FAILCRITICALERRORS, SEM_NOGPFAULTERRORBOX, SEM_NOOPENFILEERRORBOX = 0x1, 0x2, 0x8000
        ctypes.windll.kernel32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX)
    except Exception:
        pass


def main() -> None:
    quiet_windows_errors()
    taskbar.set_process_app_id()
    api = Api()
    dark = window_theme.resolve(settings.load_settings()["theme"])
    window = webview.create_window(
        APP_NAME,
        ui_entry(),
        js_api=api,
        width=1040,
        height=760,
        min_size=(780, 580),
        # La interfaz no pinta fondo hasta saber el tema: así no hay destello claro.
        background_color=window_theme.background(dark),
        text_select=False,
    )
    icon = find_icon()
    api._attach(window, Notifier(window, icon))

    def on_closing():
        if api._manager.pending_count() > 0:
            ok = window.create_confirmation_dialog(
                "Descargas pendientes",
                "Las descargas que faltan se pausarán y seguirán cuando vuelvas a abrir MisterDescarga. ¿Cerrar?",
            )
            if not ok:
                return False
        api._shutdown()
        return True

    window.events.closing += on_closing
    window.events.shown += lambda: setup_native_window(window, api, icon, dark)
    window.events.loaded += api._start_background
    webview.start(debug=os.environ.get("MD_DEBUG") == "1", http_server=True)


def report_crash(exc: BaseException) -> None:
    """Sin consola (pythonw) los errores no se verían: los guardamos y avisamos."""
    import traceback

    from paths import CONFIG_DIR

    log = CONFIG_DIR / "error.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
    except OSError:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, f"MisterDescarga no pudo iniciar:\n\n{exc}\n\nDetalles en:\n{log}", APP_NAME, 0x10
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        report_crash(exc)
        sys.exit(1)
