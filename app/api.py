"""Puente entre la interfaz (JavaScript) y Python.

pywebview expone los métodos públicos de esta clase como `window.pywebview.api.*`.
Todo lo interno empieza con "_" para que no se exponga.
"""

import ctypes
import json
import os
import threading
import time
import traceback
from pathlib import Path

import settings
import tools
import updates
import window_theme
from downloader import DownloadManager, get_info, open_in_explorer
from version import GITHUB_REPO, __version__

YTDLP_CHECK_EVERY = 20 * 3600  # revisar yt-dlp como mucho una vez al día


def _ok(data=None) -> dict:
    return {"ok": True, "data": data}


def _fail(exc: Exception | str) -> dict:
    return {"ok": False, "error": str(exc)}


def _read_clipboard_text() -> str:
    """Lee texto del portapapeles de Windows sin dependencias extra."""
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


class Api:
    def __init__(self):
        self._window = None
        self._notifier = None
        self._hwnd = 0
        self._manager = DownloadManager(self._emit_job, self._on_job_finished)
        self._setup_lock = threading.Lock()
        self._ytdlp_updating = False
        self._app_update: dict | None = None
        # Lo que quedó pendiente al cerrar vuelve a la cola, pero espera a que
        # arranque el programa (y se revise yt-dlp) antes de empezar.
        self._manager.set_paused(True)
        self._manager.restore()

    # ---------- internos ----------
    def _attach(self, window, notifier=None) -> None:
        self._window = window
        self._notifier = notifier

    def _set_hwnd(self, hwnd: int) -> None:
        self._hwnd = hwnd
        if self._notifier:
            self._notifier.set_hwnd(hwnd)

    def _start_background(self) -> None:
        """Tareas al abrir: actualizar yt-dlp, seguir la cola y buscar versión nueva."""
        if getattr(self, "_started", False):
            return  # el evento "loaded" puede repetirse si la página se recarga
        self._started = True
        threading.Thread(target=self._startup_ytdlp, daemon=True).start()
        threading.Thread(target=self._startup_app_update, daemon=True).start()

    def _startup_ytdlp(self) -> None:
        if not tools.tools_ready():
            return  # setup_tools() reanuda la cola cuando termina
        try:
            self._auto_update_ytdlp()
        finally:
            self._manager.set_paused(False)

    def _auto_update_ytdlp(self) -> None:
        if not settings.load_settings()["auto_update_ytdlp"]:
            return
        last = settings.load_state().get("ytdlp_checked", 0)
        if not isinstance(last, (int, float)) or time.time() - last < YTDLP_CHECK_EVERY:
            return
        self._ytdlp_updating = True
        self._js("__mdEvent", {"type": "ytdlp", "status": "updating"})
        before = tools.ytdlp_version()
        try:
            tools.update_ytdlp()
            settings.update_state(ytdlp_checked=time.time())
        except Exception:
            traceback.print_exc()  # sin conexión: se intenta la próxima vez
        finally:
            self._ytdlp_updating = False
        after = tools.ytdlp_version()
        self._js("__mdEvent", {
            "type": "ytdlp", "status": "done", "version": after, "changed": bool(after) and after != before,
        })

    def _startup_app_update(self) -> None:
        try:
            info = updates.check()
        except Exception:
            return
        self._app_update = info
        if info["newer"]:
            self._js("__mdEvent", {"type": "app-update", "update": info})

    def _on_job_finished(self, job: dict) -> None:
        if not self._notifier or not settings.load_settings()["notify_done"]:
            return
        if self._notifier.window_active():
            return
        if job["status"] == "done":
            text = job["title"]
            if job["playlist"]:
                text += f"\n{job['files']} archivos"
            target = job["folder"] if job["playlist"] else (job["filepath"] or job["folder"])
            self._notifier.show("Descarga lista", text, target)
        else:
            self._notifier.show("No se pudo descargar", f"{job['title']}\n{job['error']}")

    def _js(self, fn: str, payload) -> None:
        if self._window is None:
            return
        try:
            self._window.evaluate_js(f"window.{fn} && window.{fn}({json.dumps(payload)})")
        except Exception:
            pass

    def _emit_job(self, job: dict) -> None:
        self._js("__mdJob", job)

    def _shutdown(self) -> None:
        self._manager.shutdown()
        if self._notifier:
            self._notifier.dispose()

    # ---------- estado y ajustes ----------
    def get_state(self) -> dict:
        return _ok({
            "version": __version__,
            "settings": settings.load_settings(),
            "tools_ready": tools.tools_ready(),
            "missing_tools": tools.missing_tools(),
            "ffmpeg": tools.ffmpeg_status()[0] if tools.tools_ready() else "missing",
            "jobs": self._manager.list_jobs(),
            "ytdlp_updating": self._ytdlp_updating,
            "app_update": self._app_update if self._app_update and self._app_update["newer"] else None,
        })

    def save_settings(self, data: dict) -> dict:
        try:
            current = settings.load_settings()
            current.update(data or {})
            return _ok(settings.save_settings(current))
        except Exception as exc:
            return _fail(exc)

    def choose_folder(self) -> dict:
        try:
            import webview

            start = settings.load_settings()["download_dir"]
            result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
            if not result:
                return _ok(None)
            folder = result[0] if isinstance(result, (list, tuple)) else result
            current = settings.load_settings()
            current["download_dir"] = folder
            return _ok(settings.save_settings(current))
        except Exception as exc:
            return _fail(exc)

    def read_clipboard(self) -> dict:
        try:
            return _ok(_read_clipboard_text().strip()[:2000])
        except Exception:
            return _ok("")

    # ---------- herramientas ----------
    def setup_tools(self) -> dict:
        """Descarga yt-dlp/ffmpeg/deno en segundo plano; avisa por window.__mdSetup."""
        if not self._setup_lock.acquire(blocking=False):
            return _ok("running")

        def progress(tid, name, pct, done, total):
            self._js("__mdSetup", {"id": tid, "name": name, "pct": pct, "done": done, "total": total})

        def worker():
            fresh_ytdlp = not tools.YTDLP.exists()
            try:
                tools.install_missing(progress)
                tools.reset_ffmpeg_cache()
                if fresh_ytdlp and tools.YTDLP.exists():
                    settings.update_state(ytdlp_checked=time.time())  # recién bajado: es el último
                self._js("__mdSetup", {"finished": True, "ffmpeg": tools.ffmpeg_status()[0]})
            except Exception as exc:
                traceback.print_exc()
                self._js("__mdSetup", {"error": f"No se pudieron descargar las herramientas: {exc}"})
            finally:
                self._setup_lock.release()
                if tools.tools_ready() and not self._ytdlp_updating:
                    self._manager.set_paused(False)  # sigue la cola guardada, si había

        threading.Thread(target=worker, daemon=True).start()
        return _ok("started")

    def tools_info(self) -> dict:
        state, folder = tools.ffmpeg_status()
        return _ok({
            "ytdlp": tools.ytdlp_version(),
            "bin_dir": str(tools.BIN_DIR),
            "ffmpeg": state,
            "ffmpeg_dir": folder,
        })

    def ffmpeg_state(self) -> dict:
        tools.reset_ffmpeg_cache()
        state, folder = tools.ffmpeg_status()
        return _ok({"ffmpeg": state, "ffmpeg_dir": folder})

    def reinstall_ffmpeg(self) -> dict:
        """Borra el ffmpeg actual y lo vuelve a bajar (progreso por __mdSetup)."""
        if self._manager.active_count() > 0:
            return _fail("Espera a que terminen las descargas en curso.")
        tools.remove_ffmpeg()
        return self.setup_tools()

    def apply_theme(self, dark: bool) -> dict:
        """La interfaz avisa qué tema muestra, para pintar igual la barra de título."""
        window_theme.apply_titlebar(self._hwnd, bool(dark))
        return _ok()

    def check_app_update(self) -> dict:
        try:
            info = updates.check()
        except Exception:
            return _fail("No pude revisar. Revisa tu conexión a internet.")
        self._app_update = info
        return _ok(info)

    def open_url(self, url: str) -> dict:
        """Abre en el navegador, solo enlaces de la página del proyecto."""
        if not isinstance(url, str) or not url.startswith(f"https://github.com/{GITHUB_REPO}/"):
            return _fail("Enlace no permitido.")
        os.startfile(url)  # type: ignore[attr-defined]
        return _ok()

    def update_ytdlp(self) -> dict:
        try:
            out = tools.update_ytdlp()
            return _ok({"output": out, "version": tools.ytdlp_version()})
        except Exception as exc:
            return _fail(exc)

    # ---------- descargas ----------
    def get_info(self, url: str) -> dict:
        try:
            conf = settings.load_settings()
            return _ok(get_info(url, conf["cookies_browser"]))
        except Exception as exc:
            return _fail(exc)

    def start_download(self, url: str, preset: str, playlist: bool = False,
                       title: str = "", thumbnail: str = "") -> dict:
        try:
            if not tools.tools_ready():
                return _fail("Las herramientas aún no están listas.")
            return _ok(self._manager.add(url, preset, playlist, title, thumbnail))
        except Exception as exc:
            return _fail(exc)

    def cancel(self, job_id: str) -> dict:
        self._manager.cancel(job_id)
        return _ok()

    def retry(self, job_id: str) -> dict:
        return _ok(self._manager.retry(job_id))

    def remove(self, job_id: str) -> dict:
        self._manager.remove(job_id)
        return _ok()

    def clear_finished(self) -> dict:
        self._manager.clear_finished()
        return _ok()

    # ---------- archivos ----------
    def open_path(self, path: str, select: bool = False) -> dict:
        try:
            open_in_explorer(path, select)
            return _ok()
        except Exception as exc:
            return _fail(exc)

    def open_download_dir(self) -> dict:
        try:
            folder = Path(settings.load_settings()["download_dir"])
            folder.mkdir(parents=True, exist_ok=True)
            open_in_explorer(str(folder))
            return _ok()
        except Exception as exc:
            return _fail(exc)

    # ---------- historial ----------
    def get_history(self) -> dict:
        return _ok(settings.load_history())

    def clear_history(self) -> dict:
        settings.clear_history()
        return _ok()
