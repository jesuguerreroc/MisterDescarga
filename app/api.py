"""Puente entre la interfaz (JavaScript) y Python.

pywebview expone los métodos públicos de esta clase como `window.pywebview.api.*`.
Todo lo interno empieza con "_" para que no se exponga.
"""

import ctypes
import json
import threading
import traceback
from pathlib import Path

import settings
import tools
from downloader import DownloadManager, get_info, open_in_explorer
from version import __version__


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
        self._manager = DownloadManager(self._emit_job)
        self._setup_lock = threading.Lock()

    # ---------- internos ----------
    def _attach(self, window) -> None:
        self._window = window

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

    # ---------- estado y ajustes ----------
    def get_state(self) -> dict:
        return _ok({
            "version": __version__,
            "settings": settings.load_settings(),
            "tools_ready": tools.tools_ready(),
            "missing_tools": tools.missing_tools(),
            "ffmpeg": tools.ffmpeg_status()[0] if tools.tools_ready() else "missing",
            "jobs": self._manager.list_jobs(),
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
            try:
                tools.install_missing(progress)
                tools.reset_ffmpeg_cache()
                self._js("__mdSetup", {"finished": True, "ffmpeg": tools.ffmpeg_status()[0]})
            except Exception as exc:
                traceback.print_exc()
                self._js("__mdSetup", {"error": f"No se pudieron descargar las herramientas: {exc}"})
            finally:
                self._setup_lock.release()

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
