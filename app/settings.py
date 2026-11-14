"""Configuración e historial, guardados en datos/ajustes (ver paths.py)."""

import json
import os
import threading
from pathlib import Path

from paths import CONFIG_DIR
from version import APP_NAME

SETTINGS_FILE = CONFIG_DIR / "settings.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
QUEUE_FILE = CONFIG_DIR / "cola.json"  # descargas pendientes al cerrar
STATE_FILE = CONFIG_DIR / "estado.json"  # datos internos (p. ej. cuándo se revisó yt-dlp)
HISTORY_MAX = 200

PRESETS = {"mp4_best", "mp4_1080", "mp4_720", "mp4_480", "mp3_320", "mp3_192", "m4a"}
BROWSERS = {"", "chrome", "edge", "firefox", "brave", "opera", "vivaldi"}
THEMES = {"system", "light", "dark"}


def _default_download_dir() -> str:
    return str(Path.home() / "Downloads" / APP_NAME)


DEFAULTS = {
    "download_dir": _default_download_dir(),
    "default_preset": "mp4_best",
    "max_concurrent": 2,
    "cookies_browser": "",
    "watch_clipboard": True,
    "notify_done": True,
    "auto_update_ytdlp": True,
    "theme": "system",
}

_lock = threading.Lock()


def _read_json(path: Path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, data) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_settings() -> dict:
    data = dict(DEFAULTS)
    stored = _read_json(SETTINGS_FILE, {})
    if isinstance(stored, dict):
        data.update({k: v for k, v in stored.items() if k in DEFAULTS})
    return sanitize(data)


def sanitize(data: dict) -> dict:
    out = dict(DEFAULTS)
    out.update({k: v for k, v in data.items() if k in DEFAULTS})
    if not isinstance(out["download_dir"], str) or not out["download_dir"].strip():
        out["download_dir"] = _default_download_dir()
    if out["default_preset"] not in PRESETS:
        out["default_preset"] = DEFAULTS["default_preset"]
    try:
        out["max_concurrent"] = max(1, min(4, int(out["max_concurrent"])))
    except (TypeError, ValueError):
        out["max_concurrent"] = DEFAULTS["max_concurrent"]
    if out["cookies_browser"] not in BROWSERS:
        out["cookies_browser"] = ""
    for key in ("watch_clipboard", "notify_done", "auto_update_ytdlp"):
        out[key] = bool(out[key])
    if out["theme"] not in THEMES:
        out["theme"] = DEFAULTS["theme"]
    return out


def save_settings(data: dict) -> dict:
    clean = sanitize(data)
    with _lock:
        _write_json(SETTINGS_FILE, clean)
    return clean


def load_history() -> list:
    data = _read_json(HISTORY_FILE, [])
    return data if isinstance(data, list) else []


def add_history(entry: dict) -> None:
    with _lock:
        items = load_history()
        items.insert(0, entry)
        _write_json(HISTORY_FILE, items[:HISTORY_MAX])


def clear_history() -> None:
    with _lock:
        _write_json(HISTORY_FILE, [])


# ---------- cola pendiente ----------
def load_queue() -> list:
    data = _read_json(QUEUE_FILE, [])
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def save_queue(items: list) -> None:
    with _lock:
        _write_json(QUEUE_FILE, items)


# ---------- estado interno ----------
def load_state() -> dict:
    data = _read_json(STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def update_state(**values) -> None:
    with _lock:
        data = load_state()
        data.update(values)
        _write_json(STATE_FILE, data)
