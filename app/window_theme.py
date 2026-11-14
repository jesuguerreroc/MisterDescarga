"""Tema claro/oscuro de la ventana: barra de título del mismo color que la app."""

import ctypes
import winreg

# Colores de la interfaz (ui/src/index.css): papel y tinta.
LIGHT = {"caption": (0xF4, 0xF2, 0xED), "text": (0x17, 0x16, 0x0F)}
DARK = {"caption": (0x16, 0x15, 0x0F), "text": (0xF2, 0xEF, 0xE4)}

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_CAPTION_COLOR = 35  # Windows 11
_DWMWA_TEXT_COLOR = 36  # Windows 11


def system_is_dark() -> bool:
    """Lee (solo lee) si Windows está en modo oscuro para las apps."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        with key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except OSError:
        return False


def resolve(theme: str) -> bool:
    """True si hay que mostrar el tema oscuro."""
    return theme == "dark" or (theme == "system" and system_is_dark())


def background(dark: bool) -> str:
    r, g, b = (DARK if dark else LIGHT)["caption"]
    return f"#{r:02x}{g:02x}{b:02x}"


def apply_titlebar(hwnd: int, dark: bool) -> None:
    if not hwnd:
        return
    try:
        dwm = ctypes.windll.dwmapi
        palette = DARK if dark else LIGHT

        def set_attr(attr: int, value: int) -> None:
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v))

        def colorref(rgb: tuple[int, int, int]) -> int:
            r, g, b = rgb
            return r | (g << 8) | (b << 16)

        set_attr(_DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)
        set_attr(_DWMWA_CAPTION_COLOR, colorref(palette["caption"]))
        set_attr(_DWMWA_TEXT_COLOR, colorref(palette["text"]))
    except Exception:
        pass
