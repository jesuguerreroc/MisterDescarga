"""Dónde guarda la app sus datos: siempre en la carpeta `datos/` junto al programa.

MisterDescarga es portátil: no escribe nada en AppData ni en el registro. Las
herramientas, los ajustes y el historial viven en `datos/`, así la carpeta se puede
llevar en un USB o borrar sin dejar rastros.

- Versión portátil: `datos/` está al lado de MisterDescarga.exe.
- Desde el código fuente: `datos/` está en la raíz del proyecto (ignorada por git).
"""

import sys
from pathlib import Path


def _app_root() -> Path:
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "sistema" / "portable.txt").exists():
        return exe_dir
    return Path(__file__).resolve().parent.parent  # raíz del proyecto


APP_ROOT = _app_root()
DATA_DIR = APP_ROOT / "datos"
BIN_DIR = DATA_DIR / "herramientas"
CONFIG_DIR = DATA_DIR / "ajustes"
