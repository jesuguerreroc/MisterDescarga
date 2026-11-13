"""Motor de descargas: ejecuta yt-dlp.exe y traduce su salida a estado de cada descarga."""

import json
import os
import re
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
ID_PRINT = "video:MDID|%(id)s"

SINGLE_TEMPLATE = "%(title).120B [%(id)s].%(ext)s"
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

    def to_dict(self) -> dict:
        return asdict(self)


class DownloadManager:
    def __init__(self, notify: Callable[[dict], None]):
        self._notify = notify
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._procs: dict[str, subprocess.Popen] = {}
        self._canceled: set[str] = set()
        self._lock = threading.RLock()
        self._last_push: dict[str, float] = {}

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
        self._push(job, force=True)
        self._pump()
        return job.to_dict()

    def cancel(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in ("done", "error", "canceled"):
                return
            self._canceled.add(job_id)
            proc = self._procs.get(job_id)
            if job.status == "queued":
                job.status = "canceled"
        if proc and proc.poll() is None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, creationflags=CREATE_NO_WINDOW,
            )
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
            if job and job.status in ("done", "error", "canceled"):
                del self._jobs[job_id]

    def clear_finished(self) -> None:
        with self._lock:
            for jid in [j.id for j in self._jobs.values() if j.status in ("done", "error", "canceled")]:
                del self._jobs[jid]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ("downloading", "processing"))

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._procs.keys())
        for jid in ids:
            self.cancel(jid)

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

    def _pump(self) -> None:
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
            "-P", conf["download_dir"],
            "-o", PLAYLIST_TEMPLATE if job.playlist else SINGLE_TEMPLATE,
            "--progress-template", PROGRESS_TEMPLATE,
            "--progress-template", POST_TEMPLATE,
            "--print", ITEM_PRINT,
            "--print", FILE_PRINT,
            "--print", ID_PRINT,
            *_cookie_args(conf["cookies_browser"]),
            *preset_args(job.preset, bool(ffmpeg_dir)),
        ]
        cmd += ["--yes-playlist", "--ignore-errors"] if job.playlist else ["--no-playlist"]
        cmd.append(job.url)
        return cmd

    def _run(self, job: Job) -> None:
        conf = settings.load_settings()
        Path(conf["download_dir"]).mkdir(parents=True, exist_ok=True)
        before = _list_dir(conf["download_dir"])
        self._push(job, force=True)

        ff_state, ffmpeg_dir = ffmpeg_status()
        if ff_state != "ok":
            job.warning = NO_FFMPEG_WARNING

        errors: list[str] = []
        ids: set[str] = set()  # IDs de video de esta descarga (para limpiar solo lo suyo)
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
            if job.id in self._canceled:
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
                    job.filepath = path
                    job.files += 1
                    if not job.folder:
                        job.folder = str(Path(path).parent)
                    if job.playlist and job.item_count:
                        job.progress = min(100.0, job.item_index / job.item_count * 100)
                    self._push(job, force=True)
            elif line.startswith("MDID|"):
                ids.add(line.split("|", 1)[1].strip())
            elif line.startswith("ERROR"):
                errors.append(line)

        proc.wait()
        with self._lock:
            self._procs.pop(job.id, None)
            was_canceled = job.id in self._canceled
            self._canceled.discard(job.id)

        if was_canceled:
            job.status = "canceled"
            _remove_leftovers(conf["download_dir"], before, ids, job.playlist)
        elif job.files > 0:
            job.status, job.progress = "done", 100.0
            if proc.returncode != 0 and errors:
                note = f"Algunos elementos fallaron ({len(errors)})."
                job.warning = f"{job.warning} {note}".strip()
        elif proc.returncode == 0 and not errors:
            # yt-dlp terminó bien pero no imprimió ruta (p. ej. ya existía).
            job.status, job.progress = "done", 100.0
            job.folder = job.folder or conf["download_dir"]
        else:
            _remove_leftovers(conf["download_dir"], before, ids, job.playlist)
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
        self._pump()


# Restos que yt-dlp deja si una descarga falla o se cancela.
_LEFTOVER = re.compile(r"(\.part(-Frag\d+)?|\.ytdl|\.temp|\.jpe?g|\.webp|\.png|\.f\d+\.\w+)$", re.IGNORECASE)


def _list_dir(folder: str) -> set[str]:
    try:
        return {e.name for e in os.scandir(folder)}
    except OSError:
        return set()


def _remove_leftovers(folder: str, before: set[str], ids: set[str], playlist: bool) -> None:
    """Borra solo archivos temporales NUEVOS de esta descarga.

    Un archivo suelto se borra únicamente si lleva el [id] de uno de sus videos,
    así nunca se tocan descargas paralelas ni archivos que ya estaban.
    """
    tags = {f"[{i}]" for i in ids if i and i != "NA"}
    for name in _list_dir(folder) - before:
        path = Path(folder) / name
        try:
            if path.is_file() and _LEFTOVER.search(name) and any(t in name for t in tags):
                path.unlink()
            elif path.is_dir() and playlist:  # carpeta de una playlist que falló
                for f in path.iterdir():
                    if f.is_file() and _LEFTOVER.search(f.name):
                        f.unlink()
                if not any(path.iterdir()):
                    path.rmdir()
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
