"""Descarga y gestiona los ejecutables externos: yt-dlp, ffmpeg y deno.

Se guardan en la carpeta de datos (ver paths.py) para que el programa pese poco
y yt-dlp se pueda actualizar sin recompilar.
"""

import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from paths import BIN_DIR
from version import APP_NAME, __version__

YTDLP = BIN_DIR / "yt-dlp.exe"
FFMPEG = BIN_DIR / "ffmpeg.exe"
DENO = BIN_DIR / "deno.exe"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

GYAN_FALLBACK = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
GYAN_GITHUB_API = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"

# (id, nombre visible, url, archivo final, tipo)
TOOLS = [
    (
        "ytdlp",
        "El motor de descargas (yt-dlp)",
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
        YTDLP,
        "exe",
    ),
    (
        # Versión estable de Gyan: la más difundida en Windows (la misma de winget), así
        # tiene reputación ante Smart App Control. La URL real se resuelve en _ffmpeg_url().
        "ffmpeg",
        "El que junta video y audio (FFmpeg)",
        GYAN_FALLBACK,
        FFMPEG,
        "ffmpeg_zip",
    ),
    (
        "deno",
        "Ayudante para YouTube (Deno)",
        "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
        DENO,
        "deno_zip",
    ),
]

ProgressFn = Callable[[str, str, float, int, int], None]


def missing_tools() -> list[str]:
    return [tid for tid, _n, _u, target, _k in TOOLS if not target.exists()]


def tools_ready() -> bool:
    # ffmpeg es opcional: sin él se descarga igual, con calidad limitada.
    return YTDLP.exists() and DENO.exists()


def tool_env() -> dict:
    """Entorno para los subprocesos: bin primero en PATH (yt-dlp encuentra deno) y UTF-8."""
    env = os.environ.copy()
    env["PATH"] = str(BIN_DIR) + os.pathsep + env.get("PATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _download(url: str, dest: Path, on_progress: Callable[[int, int], None]) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                on_progress(done, total)


def _ffmpeg_url() -> str:
    """Espejo de Gyan en GitHub (mucho más rápido que gyan.dev); si falla, gyan.dev."""
    import json

    try:
        req = urllib.request.Request(GYAN_GITHUB_API, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.load(resp)
        for asset in release.get("assets", []):
            if asset.get("name", "").endswith("essentials_build.zip"):
                return asset["browser_download_url"]
    except Exception:
        pass
    return GYAN_FALLBACK


def _extract_ffmpeg(zip_path: Path) -> None:
    """Copia ffmpeg.exe, ffprobe.exe y sus DLL si las hubiera (carpeta bin/ del zip)."""
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            parts = member.filename.replace("\\", "/").split("/")
            if member.is_dir() or len(parts) < 2 or parts[-2] != "bin":
                continue
            name = parts[-1]
            if name.lower().startswith("ffplay"):
                continue
            with zf.open(member) as src, open(BIN_DIR / name, "wb") as dst:
                shutil.copyfileobj(src, dst)
    reset_ffmpeg_cache()


# ---------- detección de ffmpeg ----------
# Windows con "Smart App Control" puede bloquear ejecutables sin firma.
_INTEGRITY_VIOLATION = 0xC0E90002
_ERROR_INTEGRITY_POLICY = 4551
_ffmpeg_cache: tuple[str, str] | None = None  # (estado, carpeta)


def _probe(exe: Path) -> str:
    """'ok' | 'blocked' | 'broken'"""
    try:
        r = subprocess.run(
            [str(exe), "-version"], capture_output=True, timeout=20, creationflags=CREATE_NO_WINDOW
        )
    except OSError as exc:
        return "blocked" if getattr(exc, "winerror", None) == _ERROR_INTEGRITY_POLICY else "broken"
    except subprocess.SubprocessError:
        return "broken"
    if r.returncode == 0:
        return "ok"
    return "blocked" if (r.returncode & 0xFFFFFFFF) == _INTEGRITY_VIOLATION else "broken"


def reset_ffmpeg_cache() -> None:
    global _ffmpeg_cache
    _ffmpeg_cache = None


def ffmpeg_status() -> tuple[str, str]:
    """Devuelve (estado, carpeta). estado: 'ok' | 'blocked' | 'missing'.

    Usa el ffmpeg descargado por la app; si no sirve, uno instalado en el sistema (PATH).
    """
    global _ffmpeg_cache
    if _ffmpeg_cache is not None:
        return _ffmpeg_cache
    state = "missing"
    if FFMPEG.exists():
        state = _probe(FFMPEG)
        if state == "ok":
            _ffmpeg_cache = ("ok", str(BIN_DIR))
            return _ffmpeg_cache
    system = shutil.which("ffmpeg")
    if system and Path(system).resolve() != FFMPEG.resolve() and _probe(Path(system)) == "ok":
        _ffmpeg_cache = ("ok", str(Path(system).parent))
        return _ffmpeg_cache
    _ffmpeg_cache = ("blocked" if state == "blocked" else "missing", "")
    return _ffmpeg_cache


def _extract_single(zip_path: Path, exe_name: str, target: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.filename.replace("\\", "/").split("/")[-1].lower() == exe_name:
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                return
    raise RuntimeError(f"No se encontró {exe_name} dentro del zip")


def install_missing(on_progress: ProgressFn) -> None:
    """Descarga las herramientas que falten. on_progress(id, nombre, pct, hechos, total)."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for tid, name, url, target, kind in TOOLS:
        if target.exists():
            on_progress(tid, name, 100.0, 0, 0)
            continue

        def report(done: int, total: int, tid=tid, name=name) -> None:
            pct = (done / total * 100) if total else 0.0
            on_progress(tid, name, pct, done, total)

        try:
            with tempfile.TemporaryDirectory(prefix="md_") as tmp:
                tmp_file = Path(tmp) / ("download.exe" if kind == "exe" else "download.zip")
                _download(_ffmpeg_url() if tid == "ffmpeg" else url, tmp_file, report)
                if kind == "exe":
                    shutil.move(str(tmp_file), target)
                elif kind == "ffmpeg_zip":
                    _extract_ffmpeg(tmp_file)
                elif kind == "deno_zip":
                    _extract_single(tmp_file, "deno.exe", target)
            if not target.exists():
                raise RuntimeError(f"No se pudo instalar {name}")
        except Exception:
            if tid == "ffmpeg":  # opcional: seguimos sin él
                on_progress(tid, name, 100.0, 0, 0)
                continue
            raise
        on_progress(tid, name, 100.0, 0, 0)


def remove_ffmpeg() -> None:
    """Borra el ffmpeg descargado (y sus DLL) para volver a instalarlo."""
    for f in BIN_DIR.glob("*"):
        low = f.name.lower()
        if low.startswith(("ffmpeg", "ffprobe", "av", "sw", "postproc")) and f.suffix.lower() in (".exe", ".dll"):
            try:
                f.unlink()
            except OSError:
                pass
    reset_ffmpeg_cache()


def run_tool(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=tool_env(),
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def ytdlp_version() -> str:
    if not YTDLP.exists():
        return ""
    try:
        return run_tool([str(YTDLP), "--version"], timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def update_ytdlp() -> str:
    """Ejecuta `yt-dlp -U` y devuelve la salida legible."""
    if not YTDLP.exists():
        raise RuntimeError("yt-dlp no está instalado todavía")
    result = run_tool([str(YTDLP), "-U"], timeout=180)
    out = (result.stdout + "\n" + result.stderr).strip()
    return out or "Listo."
