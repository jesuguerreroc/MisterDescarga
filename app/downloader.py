"""Motor de descargas: ejecuta yt-dlp.exe y traduce su salida a estado de cada descarga."""

import ctypes
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import settings
from tools import CREATE_NO_WINDOW, YTDLP, ffmpeg_status, tool_env

PROGRESS_TEMPLATE = (
    "download:MDPROG|%(progress.downloaded_bytes)s|%(progress.total_bytes)s"
    "|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s"
    "|%(info.vcodec)s"
)
POST_TEMPLATE = "postprocess:MDPOST|%(progress.postprocessor)s|%(progress.status)s"
ITEM_PRINT = "before_dl:MDITEM|%(playlist_index)s|%(n_entries)s|%(format_id)s|%(title)s"
FILE_PRINT = "after_move:MDFILE|%(filepath)s"

# Cada descarga se baja en <carpeta>/.descargando/<id>/ y al terminar cada archivo se
# mueve a la carpeta final. Así los nombres quedan limpios (sin el [id] del video),
# los temporales nunca se mezclan con otros archivos y se puede continuar otro día.
STAGING_NAME = ".descargando"
SINGLE_TEMPLATE = "%(title).120B.%(ext)s"
PLAYLIST_TEMPLATE = "%(playlist_title,playlist_id).80B/%(playlist_index)03d - %(title).120B.%(ext)s"

AUDIO_EXTRAS = ["--embed-thumbnail", "--convert-thumbnails", "jpg", "--embed-metadata"]
VIDEO_SORT = ["-S", "res,vcodec:h264,acodec:m4a", "--merge-output-format", "mp4", "--embed-metadata"]


def _video(height: int | None) -> list[str]:
    if height is None:
        return ["-f", "bv*+ba/b", *VIDEO_SORT]
    fmt = f"bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b"
    return ["-f", fmt, *VIDEO_SORT]


PRESET_ARGS: dict[str, list[str]] = {
    "mp4_best": _video(None),
    "mp4_1080": _video(1080),
    "mp4_720": _video(720),
    "mp4_480": _video(480),
    "mp3_320": ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "320K", *AUDIO_EXTRAS],
    "mp3_192": ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "192K", *AUDIO_EXTRAS],
    "m4a": ["-f", "ba[ext=m4a]/ba/b", "-x", "--audio-format", "m4a", *AUDIO_EXTRAS],
}

PRESET_HEIGHT = {"mp4_best": None, "mp4_1080": 1080, "mp4_720": 720, "mp4_480": 480}


def preset_args(preset: str, has_ffmpeg: bool) -> list[str]:
    """Argumentos de formato. Sin ffmpeg solo se puede bajar un archivo ya combinado."""
    if has_ffmpeg:
        return PRESET_ARGS[preset]
    if preset in PRESET_HEIGHT:
        h = PRESET_HEIGHT[preset]
        if h is None:
            return ["-f", "b[ext=mp4]/b"]
        return ["-f", f"b[height<={h}][ext=mp4]/b[height<={h}]/b"]
    return ["-f", "ba[ext=m4a]/ba/b"]


NO_FFMPEG_WARNING = (
    "FFmpeg no está disponible: se descargó en calidad limitada y sin convertir. "
    "Mira «FFmpeg» en Ajustes."
)

FRIENDLY_ERRORS = [
    ("unsupported url", "Ese enlace o sitio no es compatible."),
    ("is not a valid url", "Eso no parece un enlace válido."),
    ("sign in to confirm", "El sitio pide iniciar sesión. Activa «Usar cookies del navegador» en Ajustes."),
    ("login required", "El sitio pide iniciar sesión. Activa «Usar cookies del navegador» en Ajustes."),
    ("logged-in", "El sitio pide iniciar sesión. Activa «Usar cookies del navegador» en Ajustes."),
    ("use --cookies", "El sitio pide iniciar sesión. Activa «Usar cookies del navegador» en Ajustes."),
    ("private video", "Es un video privado."),
    ("video unavailable", "El video no está disponible."),
    ("this video is not available", "El video no está disponible en tu país o fue eliminado."),
    ("confirm your age", "Contenido con restricción de edad. Activa «Usar cookies del navegador» en Ajustes."),
    ("age-restricted", "Contenido con restricción de edad. Activa «Usar cookies del navegador» en Ajustes."),
    ("http error 403", "El sitio rechazó la descarga (403). Prueba «Actualizar yt-dlp» en Ajustes."),
    ("http error 429", "Demasiadas solicitudes. Espera un rato e inténtalo de nuevo."),
    ("could not copy", "No se pudieron leer las cookies del navegador. Ciérralo o usa Firefox."),
    ("failed to decrypt", "No se pudieron leer las cookies del navegador. Ciérralo o usa Firefox."),
    ("unable to download webpage", "No se pudo abrir la página. Revisa tu conexión."),
    ("getaddrinfo failed", "Sin conexión a internet."),
]


def friendly_error(raw: str) -> str:
    low = raw.lower()
    for needle, msg in FRIENDLY_ERRORS:
        if needle in low:
            return msg
    return raw.replace("ERROR: ", "").strip() or "Error desconocido."


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cookie_args(browser: str) -> list[str]:
    return ["--cookies-from-browser", browser] if browser else []


def _best_thumbnail(info: dict) -> str:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = info.get("thumbnails") or []
    for t in reversed(thumbs):
        if t.get("url"):
            return t["url"]
    return ""


def get_info(url: str, cookies_browser: str = "") -> dict:
    """Consulta el enlace sin descargar. Devuelve datos para la vista previa."""
    url = url.strip()
    if not url:
        raise ValueError("Pega un enlace primero.")
    cmd = [
        str(YTDLP), "-J", "--no-playlist", "--flat-playlist", "--no-warnings",
        *_cookie_args(cookies_browser), url,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=tool_env(), timeout=120, creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("El sitio tardó demasiado en responder.")
    if proc.returncode != 0 or not proc.stdout.strip():
        errors = [l for l in proc.stderr.splitlines() if l.startswith("ERROR")]
        raise RuntimeError(friendly_error(errors[-1] if errors else proc.stderr.strip()))

    info = json.loads(proc.stdout)
    is_playlist = info.get("_type") == "playlist"
    entries = [e for e in (info.get("entries") or []) if e]
    thumbnail = _best_thumbnail(info)
    if not thumbnail and entries:
        thumbnail = _best_thumbnail(entries[0])

    formats = info.get("formats") or []
    heights = sorted({int(f["height"]) for f in formats if f.get("height") and f.get("vcodec") != "none"})
    has_video = bool(heights) or any(f.get("vcodec") not in (None, "none") for f in formats)
    if not formats:
        has_video = info.get("vcodec") != "none"

    query = parse_qs(urlparse(url).query)
    return {
        "url": url,
        "title": info.get("title") or info.get("id") or url,
        "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "",
        "duration": info.get("duration") or 0,
        "thumbnail": thumbnail,
        "site": info.get("extractor_key") or info.get("extractor") or "",
        "is_playlist": is_playlist,
        "count": info.get("playlist_count") or len(entries),
        "maybe_playlist": (not is_playlist) and "list" in query,
        "has_video": has_video if not is_playlist else True,
        "max_height": heights[-1] if heights else 0,
        "entries": [e.get("title") or e.get("id") or "" for e in entries[:8]],
    }


@dataclass
class Job:
    url: str
    preset: str
    playlist: bool
    title: str = ""
    thumbnail: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "queued"  # queued | downloading | processing | done | error | canceled
    progress: float = 0.0
    speed: float = 0.0
    eta: float = 0.0
    downloaded: float = 0.0
    total: float = 0.0
    stage: str = ""
    item_index: int = 0
    item_count: int = 0
    item_title: str = ""
    filepath: str = ""
    folder: str = ""
    files: int = 0
    error: str = ""
    warning: str = ""
    attempt: int = 0
    created: float = field(default_factory=time.time)
    dest: str = ""  # carpeta final (la de Ajustes al empezar)
    staging: str = ""  # carpeta temporal de esta descarga
    resumed: bool = False  # vino de la cola guardada al cerrar

    def to_dict(self) -> dict:
        return asdict(self)

    def persisted(self) -> dict:
        return {k: getattr(self, k) for k in PERSISTED}


PERSISTED = ("id", "url", "preset", "playlist", "title", "thumbnail", "created", "dest", "staging")
ACTIVE = ("queued", "downloading", "processing")
FINISHED = ("done", "error", "canceled")


class DownloadManager:
    def __init__(self, notify: Callable[[dict], None], on_finish: Callable[[dict], None] | None = None):
        self._notify = notify
        self._on_finish = on_finish
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._procs: dict[str, subprocess.Popen] = {}
        self._canceled: set[str] = set()
        self._lock = threading.RLock()
        self._last_push: dict[str, float] = {}
        self._paused = False
        self._shutting_down = False

    # ---------- API pública ----------
    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()]

    def add(self, url: str, preset: str, playlist: bool, title: str = "", thumbnail: str = "") -> dict:
        if preset not in PRESET_ARGS:
            raise ValueError("Formato no válido.")
        job = Job(url=url.strip(), preset=preset, playlist=bool(playlist), title=title or url, thumbnail=thumbnail)
        with self._lock:
            self._jobs[job.id] = job
        self._save_queue()
        self._push(job, force=True)
        self._pump()
        return job.to_dict()

    def restore(self) -> int:
        """Vuelve a poner en la cola lo que quedó pendiente al cerrar. Devuelve cuántas."""
        keep: set[str] = set()
        with self._lock:
            for d in settings.load_queue():
                try:
                    job = Job(
                        id=str(d["id"]), url=str(d["url"]), preset=str(d["preset"]),
                        playlist=bool(d.get("playlist")), title=str(d.get("title") or d["url"]),
                        thumbnail=str(d.get("thumbnail") or ""), created=float(d.get("created") or time.time()),
                        dest=str(d.get("dest") or ""), staging=str(d.get("staging") or ""), resumed=True,
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                if job.preset in PRESET_ARGS and job.id not in self._jobs:
                    self._jobs[job.id] = job
                    keep.add(job.id)
            count = len(self._jobs)
        _clean_staging(settings.load_settings()["download_dir"], keep)
        return count

    def set_paused(self, paused: bool) -> None:
        """En pausa no arranca descargas nuevas (p. ej. mientras se actualiza yt-dlp)."""
        self._paused = paused
        if not paused:
            self._pump()

    def cancel(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in FINISHED:
                return
            self._canceled.add(job_id)
            proc = self._procs.get(job_id)
            if job.status == "queued":
                job.status = "canceled"
        if proc and proc.poll() is None:
            _kill(proc)
        self._save_queue()
        self._push(job, force=True)
        self._pump()

    def retry(self, job_id: str) -> dict | None:
        with self._lock:
            old = self._jobs.get(job_id)
        if not old:
            return None
        self.remove(job_id)
        return self.add(old.url, old.preset, old.playlist, old.title, old.thumbnail)

    def remove(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in FINISHED:
                del self._jobs[job_id]

    def clear_finished(self) -> None:
        with self._lock:
            for jid in [j.id for j in self._jobs.values() if j.status in FINISHED]:
                del self._jobs[jid]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ("downloading", "processing"))

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ACTIVE)

    def shutdown(self) -> None:
        """Al cerrar: guarda lo pendiente (para seguir la próxima vez) y detiene yt-dlp.

        Las carpetas temporales se conservan: yt-dlp continúa desde los .part.
        """
        with self._lock:
            pending = [j.persisted() for j in self._jobs.values() if j.status in ACTIVE]
            self._shutting_down = True
            procs = list(self._procs.values())
        try:
            settings.save_queue(pending)
        except OSError:
            pass
        for proc in procs:
            if proc.poll() is None:
                _kill(proc)

    # ---------- internos ----------
    def _push(self, job: Job, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_push.get(job.id, 0) < 0.25:
            return
        self._last_push[job.id] = now
        try:
            self._notify(job.to_dict())
        except Exception:
            pass

    def _save_queue(self) -> None:
        with self._lock:
            if self._shutting_down:
                return
            pending = [j.persisted() for j in self._jobs.values() if j.status in ACTIVE]
        try:
            settings.save_queue(pending)
        except OSError:
            pass

    def _pump(self) -> None:
        if self._paused or self._shutting_down:
            return
        limit = settings.load_settings()["max_concurrent"]
        with self._lock:
            running = sum(1 for j in self._jobs.values() if j.status in ("downloading", "processing"))
            for job in self._jobs.values():
                if running >= limit:
                    break
                if job.status == "queued":
                    job.status = "downloading"
                    running += 1
                    threading.Thread(target=self._run, args=(job,), daemon=True).start()

    def _build_cmd(self, job: Job, conf: dict, ffmpeg_dir: str) -> list[str]:
        cmd = [
            str(YTDLP),
            "--newline", "--no-colors", "--quiet", "--progress", "--no-simulate", "--no-mtime",
            "--concurrent-fragments", "4",
            *(["--ffmpeg-location", ffmpeg_dir] if ffmpeg_dir else []),
            "-P", job.staging,
            "-o", PLAYLIST_TEMPLATE if job.playlist else SINGLE_TEMPLATE,
            "--progress-template", PROGRESS_TEMPLATE,
            "--progress-template", POST_TEMPLATE,
            "--print", ITEM_PRINT,
            "--print", FILE_PRINT,
            *_cookie_args(conf["cookies_browser"]),
            *preset_args(job.preset, bool(ffmpeg_dir)),
        ]
        cmd += ["--yes-playlist", "--ignore-errors"] if job.playlist else ["--no-playlist"]
        cmd.append(job.url)
        return cmd

    def _prepare_staging(self, job: Job, conf: dict) -> bool:
        if not job.dest:
            job.dest = conf["download_dir"]
        if not job.staging:
            job.staging = str(Path(job.dest) / STAGING_NAME / job.id)
        try:
            Path(job.staging).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            job.status, job.error = "error", f"No se pudo usar la carpeta de descargas: {exc}"
            return False
        _hide(Path(job.staging).parent)
        self._save_queue()
        return True

    def _deliver(self, job: Job, path: str) -> str:
        """Mueve un archivo terminado de la carpeta temporal a la final. Devuelve dónde quedó."""
        src = Path(path)
        try:
            rel = src.relative_to(job.staging)
        except ValueError:
            return path  # no está en la carpeta temporal: se deja donde esté
        for _ in range(8):
            target = _unique(Path(job.dest) / rel)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.rename(src, target)
                return str(target)
            except FileExistsError:
                continue  # otra descarga tomó ese nombre justo ahora
            except PermissionError:
                time.sleep(0.4)  # yt-dlp todavía lo tiene abierto
            except OSError:
                break
        return path

    def _run(self, job: Job) -> None:
        conf = settings.load_settings()
        self._push(job, force=True)
        if not self._prepare_staging(job, conf):
            self._finish(job)
            return

        ff_state, ffmpeg_dir = ffmpeg_status()
        if ff_state != "ok":
            job.warning = NO_FFMPEG_WARNING

        errors: list[str] = []
        stuck: list[str] = []  # archivos que no se pudieron mover mientras yt-dlp seguía
        merged = False  # el formato actual combina video+audio
        try:
            proc = subprocess.Popen(
                self._build_cmd(job, conf, ffmpeg_dir),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                env=tool_env(), creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            job.status, job.error = "error", f"No se pudo iniciar yt-dlp: {exc}"
            self._finish(job)
            return

        with self._lock:
            self._procs[job.id] = proc
            if job.id in self._canceled or self._shutting_down:
                proc.kill()

        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            if line.startswith("MDPROG|"):
                self._on_progress(job, line.split("|"), merged)
            elif line.startswith("MDITEM|"):
                parts = line.split("|", 4)
                merged = "+" in parts[3]
                idx, count = _num(parts[1]), _num(parts[2])
                if job.playlist:
                    job.item_index = int(idx) if idx else job.item_index + 1
                    job.item_count = int(count) if count else job.item_count
                    job.item_title = parts[4]
                elif parts[4] and parts[4] != "NA":
                    job.title = parts[4]
                job.status, job.stage = "downloading", ""
                self._push(job, force=True)
            elif line.startswith("MDPOST|"):
                parts = line.split("|")
                started = parts[2] in ("started", "processing")
                if started and job.status == "downloading" and job.downloaded > 0:
                    job.status = "processing"
                    self._push(job, force=True)
            elif line.startswith("MDFILE|"):
                path = line.split("|", 1)[1].strip()
                if path and path != "NA":
                    final = self._deliver(job, path)
                    if final == path and Path(path).is_relative_to(job.staging):
                        stuck.append(path)
                    job.filepath = final
                    job.files += 1
                    if not job.folder:
                        job.folder = str(Path(final).parent)
                    if job.playlist and job.item_count:
                        job.progress = min(100.0, job.item_index / job.item_count * 100)
                    self._push(job, force=True)
            elif line.startswith("ERROR"):
                errors.append(line)

        proc.wait()
        with self._lock:
            self._procs.pop(job.id, None)
            was_canceled = job.id in self._canceled
            self._canceled.discard(job.id)
            if self._shutting_down and not was_canceled:
                return  # se cerró el programa: queda en la cola para la próxima vez

        for path in stuck:  # yt-dlp ya terminó, ahora sí se pueden mover
            final = self._deliver(job, path)
            if job.filepath == path:
                job.filepath = final
            if job.folder == str(Path(path).parent):
                job.folder = str(Path(final).parent)

        if was_canceled:
            job.status = "canceled"
        elif job.files > 0:
            job.status, job.progress = "done", 100.0
            if proc.returncode != 0 and errors:
                note = f"Algunos elementos fallaron ({len(errors)})."
                job.warning = f"{job.warning} {note}".strip()
        elif proc.returncode == 0 and not errors:
            # yt-dlp terminó bien pero no imprimió ruta (p. ej. una lista vacía).
            job.status, job.progress = "done", 100.0
            job.folder = job.folder or job.dest
        else:
            last = errors[-1] if errors else ""
            if job.attempt == 0 and "403" in last:
                # YouTube y otros a veces rechazan una vez y aceptan al reintentar.
                job.attempt = 1
                job.progress = job.downloaded = job.total = 0.0
                job.status, job.stage = "downloading", ""
                self._run(job)
                return
            job.status = "error"
            job.error = friendly_error(last or f"yt-dlp terminó con código {proc.returncode}")
        _remove_staging(job.staging)
        self._finish(job)

    def _on_progress(self, job: Job, parts: list[str], merged: bool) -> None:
        if len(parts) < 7:
            return
        done = _num(parts[1]) or 0.0
        total = _num(parts[2]) or _num(parts[3]) or 0.0
        job.speed = _num(parts[4]) or 0.0
        job.eta = _num(parts[5]) or 0.0
        job.downloaded, job.total = done, total
        is_audio_part = parts[6] == "none"
        frac = min(1.0, done / total) if total else 0.0

        if merged:
            job.stage = "audio" if is_audio_part else "video"
            item = (0.85 + 0.15 * frac) if is_audio_part else 0.85 * frac
        else:
            job.stage = ""
            item = frac

        if job.playlist and job.item_count:
            pct = ((job.item_index - 1) + item) / job.item_count * 100
        else:
            pct = item * 100
        job.progress = max(0.0, min(99.5, pct))
        if job.status == "processing" and frac < 1.0:
            job.status = "downloading"
        if frac >= 1.0 and (not merged or is_audio_part) and not job.playlist:
            job.status = "processing"
        self._push(job, force=job.status == "processing")

    def _finish(self, job: Job) -> None:
        job.speed = job.eta = 0.0
        self._save_queue()
        self._push(job, force=True)
        if job.status == "done":
            try:
                settings.add_history({
                    "id": job.id,
                    "title": job.title,
                    "url": job.url,
                    "preset": job.preset,
                    "filepath": job.filepath,
                    "folder": job.folder,
                    "thumbnail": job.thumbnail,
                    "playlist": job.playlist,
                    "files": job.files,
                    "date": datetime.now().isoformat(timespec="seconds"),
                })
            except OSError:
                pass
        if self._on_finish and job.status in ("done", "error"):
            try:
                self._on_finish(job.to_dict())
            except Exception:
                pass
        self._pump()


# ---------- archivos ----------
_JOB_ID = re.compile(r"^[0-9a-f]{10}$")


def _kill(proc: subprocess.Popen) -> None:
    """Termina yt-dlp y sus hijos (ffmpeg)."""
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
        capture_output=True, creationflags=CREATE_NO_WINDOW,
    )
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _unique(path: Path) -> Path:
    """`Título.mp4` → `Título (2).mp4` si ya existe, y así sucesivamente."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _hide(folder: Path) -> None:
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x2
        ctypes.windll.kernel32.SetFileAttributesW(str(folder), FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


def _remove_staging(staging: str) -> None:
    """Borra la carpeta temporal de una descarga (y .descargando si quedó vacía)."""
    if not staging:
        return
    path = Path(staging)
    if path.parent.name != STAGING_NAME or not _JOB_ID.match(path.name):
        return  # por seguridad, solo carpetas creadas por nosotros
    shutil.rmtree(path, ignore_errors=True)
    try:
        path.parent.rmdir()  # solo si está vacía
    except OSError:
        pass


def _clean_staging(download_dir: str, keep: set[str]) -> None:
    """Al abrir: borra carpetas temporales viejas que no pertenezcan a la cola guardada."""
    root = Path(download_dir) / STAGING_NAME
    try:
        children = list(root.iterdir())
    except OSError:
        return
    for child in children:
        if child.is_dir() and _JOB_ID.match(child.name) and child.name not in keep:
            _remove_staging(str(child))
    try:
        root.rmdir()
    except OSError:
        pass


def open_in_explorer(path: str, select: bool = False) -> None:
    if not path:
        return
    p = Path(path)
    if select and p.exists():
        subprocess.Popen(["explorer", "/select,", str(p)])
    elif p.exists():
        os.startfile(str(p))  # type: ignore[attr-defined]
    elif p.parent.exists():
        os.startfile(str(p.parent))  # type: ignore[attr-defined]
    else:
        raise FileNotFoundError("Ya no existe ese archivo o carpeta.")
