"""Identidad de la ventana en la barra de tareas de Windows.

MisterDescarga.exe es pythonw.exe con otro nombre: no se le puede cambiar el icono
sin romper su firma digital (y Windows lo bloquearía). En su lugar le decimos a la
barra de tareas, por ventana, qué icono, nombre y comando usar. Así el botón y el
acceso anclado muestran el pingüino y abren MisterDescarga.

Propiedades usadas (System.AppUserModel.*):
  ID, RelaunchCommand, RelaunchIconResource, RelaunchDisplayNameResource.
"""

import ctypes
import uuid
from ctypes import POINTER, byref, c_ulong, c_ushort, c_void_p, c_wchar_p, wintypes

APP_ID = "MisterDescarga.App"

_HRESULT = ctypes.c_long


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "_GUID":
        u = uuid.UUID(text)
        g = cls(u.time_low, u.time_mid, u.time_hi_version)
        g.Data4[:] = list(u.bytes[8:])
        return g


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _PROPVARIANT(ctypes.Structure):
    # vt + 3 reservados + unión (puntero) con relleno: 24 bytes en 64 bits.
    _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("value", c_void_p), ("pad", c_void_p)]


_VT_LPWSTR = 31
_IID_IPropertyStore = _GUID.parse("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")
_APPUSERMODEL = "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"
_PKEY_ID = _PROPERTYKEY(_GUID.parse(_APPUSERMODEL), 5)
_PKEY_RELAUNCH_COMMAND = _PROPERTYKEY(_GUID.parse(_APPUSERMODEL), 2)
_PKEY_RELAUNCH_ICON = _PROPERTYKEY(_GUID.parse(_APPUSERMODEL), 3)
_PKEY_RELAUNCH_NAME = _PROPERTYKEY(_GUID.parse(_APPUSERMODEL), 4)


def set_process_app_id() -> None:
    """Agrupa las ventanas del proceso como MisterDescarga (no como Python)."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def set_window_identity(hwnd: int, command: str, icon: str, name: str) -> bool:
    """Debe llamarse desde el hilo de la ventana (COM ya iniciado). Devuelve True si se aplicó."""
    shell32 = ctypes.windll.shell32
    shell32.SHGetPropertyStoreForWindow.argtypes = [wintypes.HWND, POINTER(_GUID), POINTER(c_void_p)]
    shell32.SHGetPropertyStoreForWindow.restype = _HRESULT

    store = c_void_p()
    if shell32.SHGetPropertyStoreForWindow(hwnd, byref(_IID_IPropertyStore), byref(store)) != 0 or not store:
        return False

    vtbl = ctypes.cast(store, POINTER(POINTER(c_void_p)))[0]
    set_value = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, POINTER(_PROPERTYKEY), POINTER(_PROPVARIANT))(vtbl[6])
    commit = ctypes.WINFUNCTYPE(_HRESULT, c_void_p)(vtbl[7])
    release = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])

    ok = True
    try:
        # El ID va primero: sin él, Windows ignora las propiedades de relanzamiento.
        for key, text in (
            (_PKEY_ID, APP_ID),
            (_PKEY_RELAUNCH_COMMAND, command),
            (_PKEY_RELAUNCH_ICON, icon),
            (_PKEY_RELAUNCH_NAME, name),
        ):
            buf = c_wchar_p(text)  # SetValue copia el valor, basta con que viva durante la llamada
            pv = _PROPVARIANT(vt=_VT_LPWSTR, value=ctypes.cast(buf, c_void_p))
            ok = set_value(store, byref(key), byref(pv)) == 0 and ok
        ok = commit(store) == 0 and ok
    finally:
        release(store)
    return ok
