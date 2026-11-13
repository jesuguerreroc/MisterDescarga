"""Arranque de la versión portátil.

En la versión portátil, MisterDescarga.exe es el pythonw.exe oficial (firmado por la
Python Software Foundation) con otro nombre. Como Windows confía en esa firma, no lo
bloquea el "Control inteligente de aplicaciones".

Python ejecuta este archivo al iniciar. Si se abrió con doble clic (sin argumentos),
vuelve a lanzar el mismo ejecutable con sistema/app/main.py y termina. No se puede
abrir la ventana desde aquí: Python aún no terminó de iniciar y pythonnet fallaría.
"""

import os
import sys


def _hide_support_files(root: str) -> None:
    """Oculta las DLL de Python para que la carpeta se vea limpia."""
    try:
        import ctypes

        for name in os.listdir(root):
            if name.lower().endswith((".dll", "._pth")):
                ctypes.windll.kernel32.SetFileAttributesW(os.path.join(root, name), 0x2)
    except Exception:
        pass


def _relaunch() -> None:
    if os.path.basename(sys.executable).lower() != "misterdescarga.exe":
        return
    if sys.argv not in ([""], []):
        return
    root = os.path.dirname(os.path.abspath(sys.executable))
    _hide_support_files(root)
    import subprocess

    main_py = os.path.join(root, "sistema", "app", "main.py")
    subprocess.Popen([sys.executable, main_py], cwd=root, close_fds=True)
    os._exit(0)


_relaunch()
