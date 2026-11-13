"""Arma MisterDescarga: dist/MisterDescarga/ y dist/MisterDescarga-x.y.z-portable.zip.

No usa PyInstaller. Copia el Python oficial ya instalado (sus .exe y .dll están
firmados), así Windows no lo bloquea. MisterDescarga.exe es pythonw.exe renombrado
y sistema/sitecustomize.py arranca la app.

Uso (con el venv activo):
    python scripts/build_portable.py            compila la interfaz y arma el zip
    python scripts/build_portable.py --skip-ui  si ui/dist ya está compilado
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = DIST / "MisterDescarga"
SYS = OUT / "sistema"
BASE = Path(sys.base_prefix)  # la instalación real de Python (no el venv)
PYVER = f"{sys.version_info.major}{sys.version_info.minor}"

# Partes de la biblioteca estándar que la app no usa.
SKIP_LIB = {
    "site-packages", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip",
    "lib2to3", "venv", "__pycache__", "__phello__", "pydoc_data",
}
SKIP_DLLS = ("_tkinter", "tcl", "tk", "_test", "xxlimited", "_ctypes_test")

LEEME = """MisterDescarga (versión portátil)
==================================

Abrir:   doble clic en MisterDescarga.exe

No se instala nada en el computador. Todo (herramientas, ajustes e historial)
se guarda en la carpeta "datos" que está aquí mismo, así que puedes llevar
esta carpeta en un USB y usarla en cualquier PC con Windows 10 u 11.

La primera vez descarga las herramientas que necesita (yt-dlp, FFmpeg y Deno).

Los videos se guardan en Descargas\\MisterDescarga (se puede cambiar en Ajustes).

Usa el programa solo con contenido que tengas derecho a descargar.
"""


def ignore_lib(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in SKIP_LIB or n.endswith((".pyc", ".exe"))}


def main() -> None:
    from version import __version__  # noqa: PLC0415 (app/ está en sys.path abajo)

    ui = ROOT / "ui" / "dist"
    if "--skip-ui" not in sys.argv:
        npm = shutil.which("npm") or "npm"
        subprocess.run([npm, "ci"], cwd=ROOT / "ui", check=True)
        subprocess.run([npm, "run", "build"], cwd=ROOT / "ui", check=True)
    if not (ui / "index.html").exists():
        sys.exit("Falta ui/dist. Ejecuta sin --skip-ui.")

    print(f"== MisterDescarga {__version__} (portátil · Python {sys.version.split()[0]}) ==")
    # Conserva los datos de la copia local (herramientas ya bajadas, ajustes) entre armados.
    kept = DIST / "_datos_guardados"
    shutil.rmtree(kept, ignore_errors=True)
    if (OUT / "datos").exists():
        shutil.move(str(OUT / "datos"), kept)
    shutil.rmtree(OUT, ignore_errors=True)
    SYS.mkdir(parents=True)

    # 1. Ejecutable y DLL de Python
    shutil.copy2(BASE / "pythonw.exe", OUT / "MisterDescarga.exe")
    for dll in (f"python{PYVER}.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        if (BASE / dll).exists():
            shutil.copy2(BASE / dll, OUT / dll)
    (OUT / "MisterDescarga._pth").write_text(
        "sistema\\Lib\nsistema\\DLLs\nsistema\\Lib\\site-packages\nsistema\\app\nsistema\nimport site\n",
        encoding="utf-8",
    )

    # 2. Biblioteca estándar y módulos nativos
    shutil.copytree(BASE / "Lib", SYS / "Lib", ignore=ignore_lib)
    (SYS / "DLLs").mkdir()
    for f in (BASE / "DLLs").iterdir():
        if f.is_file() and not f.name.lower().startswith(SKIP_DLLS):
            shutil.copy2(f, SYS / "DLLs" / f.name)

    # 3. Dependencias (pywebview y compañía)
    site = SYS / "Lib" / "site-packages"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--no-compile", "--target", str(site),
         "-r", str(ROOT / "requirements.txt")],
        check=True,
    )
    shutil.rmtree(site / "bin", ignore_errors=True)
    for junk in site.glob("*.dist-info"):
        shutil.rmtree(junk)

    # 4. La app, la interfaz y el arranque
    shutil.copytree(ROOT / "app", SYS / "app", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ui, SYS / "ui")
    shutil.copy2(ROOT / "scripts" / "portable" / "sitecustomize.py", SYS / "sitecustomize.py")
    shutil.copy2(ROOT / "assets" / "icon.ico", SYS / "icon.ico")
    (SYS / "portable.txt").write_text("Marca de la versión portátil. No borrar.\n", encoding="utf-8")
    (OUT / "LÉEME.txt").write_text(LEEME, encoding="utf-8-sig")

    # 5. Comprimir (sin datos personales: la carpeta datos/ todavía no está)
    for old in DIST.glob("MisterDescarga-*-portable.zip"):
        old.unlink()
    zip_path = DIST / f"MisterDescarga-{__version__}-portable.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in sorted(OUT.rglob("*")):
            if f.is_file():
                zf.write(f, Path("MisterDescarga") / f.relative_to(OUT))
    if kept.exists():
        shutil.move(str(kept), OUT / "datos")

    folder_mb = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"Carpeta: {OUT}  ({folder_mb:.0f} MB)")
    print(f"Zip:     {zip_path}  ({zip_path.stat().st_size / 1024 / 1024:.0f} MB)")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "app"))
    main()
