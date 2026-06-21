import sys
import os
import ctypes
import ctypes.wintypes
from pathlib import Path

try:
    _THIS_FILE = Path(__file__).resolve()
except NameError:
    _THIS_FILE = Path(sys.argv[0]).resolve()

BIF_RETURNONLYFSDIRS = 0x0001
BIF_NEWDIALOGSTYLE = 0x0040


class _BROWSEINFOW(ctypes.Structure):
    _fields_ = [
        ("hwndOwner", ctypes.wintypes.HWND),
        ("pidlRoot", ctypes.c_void_p),
        ("pszDisplayName", ctypes.wintypes.LPWSTR),
        ("lpszTitle", ctypes.wintypes.LPCWSTR),
        ("ulFlags", ctypes.wintypes.UINT),
        ("lpfn", ctypes.c_void_p),
        ("lParam", ctypes.c_long),
        ("iImage", ctypes.c_int),
    ]


def _msgbox(title, text, buttons=0):
    return ctypes.windll.user32.MessageBoxW(0, text, title, buttons | 0x30)


def _pick_folder(title):
    ctypes.windll.ole32.CoInitialize(None)
    try:
        buf = ctypes.create_unicode_buffer(260)
        bi = _BROWSEINFOW(
            hwndOwner=None, pidlRoot=None,
            pszDisplayName=ctypes.cast(buf, ctypes.wintypes.LPWSTR),
            lpszTitle=title,
            ulFlags=BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE,
            lpfn=None, lParam=0, iImage=0,
        )
        pidl = ctypes.windll.shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if pidl:
            path_buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetPathFromIDListW(pidl, path_buf):
                return path_buf.value
            ctypes.windll.ole32.CoTaskMemFree(pidl)
        return None
    finally:
        ctypes.windll.ole32.CoUninitialize()


def _check_src(src):
    return (Path(src) / "fusion_frame" / "__init__.py").is_file()


PLUGIN_SRC = r"D:\Davinci Projects\When someone sees you trip\When someone sees you trip\Renders\src"

if not _check_src(PLUGIN_SRC):
    ret = _msgbox(
        "Fusion Frame",
        "Fusion Frame source not found at:\\n" + str(PLUGIN_SRC) + "\\n\\nThe directory may have been moved or renamed.\\n\\nClick OK to locate the new 'src' folder.",
        1,
    )
    if ret != 1:
        raise SystemExit(0)
    new_src = _pick_folder("Select the 'src' folder that contains 'fusion_frame/'")
    if not new_src or not _check_src(new_src):
        _msgbox("Fusion Frame", "Invalid folder. Please run the installer again.", 0)
        raise SystemExit(1)
    _content = _THIS_FILE.read_text(encoding="utf-8")
    _content = _content.replace('PLUGIN_SRC = r"' + str(PLUGIN_SRC) + '"', 'PLUGIN_SRC = r"' + str(new_src) + '"')
    _THIS_FILE.write_text(_content, encoding="utf-8")
    PLUGIN_SRC = new_src

sys.path.insert(0, str(Path(PLUGIN_SRC)))

import importlib
for _key in [k for k in list(sys.modules) if k.startswith("fusion_frame")]:
    del sys.modules[_key]

try:
    from fusion_frame import run as _run
except ImportError as e:
    _msgbox("Fusion Frame", "Failed to load Fusion Frame:\\n" + str(e), 0)
    raise

resolve = app.GetResolve()
_run(resolve=resolve)
