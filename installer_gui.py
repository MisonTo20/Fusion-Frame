import os
import sys
import time
import shutil
import threading
import subprocess

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_LINES = []

import dearpygui.dearpygui as dpg


def log(msg):
    ts = time.strftime("[%H:%M:%S]")
    LOG_LINES.append(f"{ts} {msg}")
    dpg.set_value("log_text", "\n".join(LOG_LINES[-500:]))
    try:
        dpg.set_y_scroll("log_child", 999999)
    except Exception:
        pass


def _powershell(script):
    """Run a PowerShell command and return (returncode, stdout, stderr)."""
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW)
    out, err = proc.communicate()
    return proc.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


# ============================================================
# Download dependencies
# ============================================================

def _install_python311(pydir):
    PY311 = os.path.join(pydir, "python.exe")

    if os.path.exists(PY311):
        log("[..] Python 3.11.9 already present")
        return PY311

    log("[..] Downloading Python 3.11.9...")
    zip_url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
    zip_file = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                            "python-3.11.9-embed-amd64.zip")
    rc, _, _ = _powershell(
        f"Invoke-WebRequest -UseBasicParsing -Uri '{zip_url}' -OutFile '{zip_file}'")
    if rc != 0:
        log("[FAIL] Download failed. Check your internet connection.")
        return None
    log("[OK] Downloaded")

    log("[..] Extracting to Python311...")
    rc, _, _ = _powershell(
        f"Expand-Archive -Path '{zip_file}' -DestinationPath '{pydir}' -Force")
    if rc != 0:
        log("[FAIL] Extract failed.")
        return None
    os.remove(zip_file)
    log("[OK] Extracted")

    log("[..] Configuring Python environment...")
    pth = os.path.join(pydir, "python311._pth")
    if os.path.exists(pth):
        content = open(pth).read().replace("#import site", "import site")
        open(pth, "w").write(content)
    log("[OK] Configured")
    return PY311


def _bootstrap_pip(PY311, pydir):
    try:
        subprocess.run([PY311, "-m", "pip", "--version"], check=True,
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log("[..] pip already installed")
        return True
    except subprocess.CalledProcessError:
        pass

    log("[..] Bootstrapping pip...")
    pth = os.path.join(pydir, "python311._pth")
    if os.path.exists(pth):
        content = open(pth).read().replace("#import site", "import site")
        open(pth, "w").write(content)
    log("[OK] Configured")

    gp = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "get-pip.py")
    log("[..] Downloading get-pip.py...")
    rc, _, _ = _powershell(
        "Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '{0}'".format(gp))
    if rc != 0:
        log("[FAIL] Failed to download get-pip.py")
        return False
    log("[OK] Downloaded")

    log("[..] Installing pip...")
    try:
        subprocess.run([PY311, gp], check=True, capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.CalledProcessError:
        log("[FAIL] pip bootstrap failed")
        return False
    os.remove(gp)
    log("[OK] pip installed")
    return True


def _pip_install(PY311, *packages):
    log(f"[..] Installing {' + '.join(packages)}...")
    try:
        subprocess.run([PY311, "-m", "pip", "install", *packages],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.CalledProcessError:
        log("[FAIL] pip install failed")
        return False
    log("[OK] Installed")
    return True


def run_download_deps():
    def task():
        log("=== Download Dependencies ===")
        pydir = os.path.join(BASE_DIR, "Python311")
        PY311 = _install_python311(pydir)
        if PY311 is None:
            return
        if not _bootstrap_pip(PY311, pydir):
            return
        if not _pip_install(PY311, "dearpygui", "psutil"):
            return

        log("[..] Downloading Fusion Frame...")
        rc, _, _ = _powershell(
            "iwr -useb 'https://raw.githubusercontent.com/MisonTo20/Fusion-Frame/refs/heads/main/FFrame.py' -OutFile '{0}\\FFrame.py'".format(BASE_DIR))
        if rc != 0:
            log("[FAIL] Failed to download Fusion Frame")
            return
        log("[OK] Fusion Frame downloaded")

        log("[..] Creating run.bat...")
        run_bat = '''\
@echo off
if not exist "%~dp0Python311\\python.exe" (
    echo Python 3.11.9 not found. Run install.bat first.
    pause
    exit /b 1
)

cd /d "%~dp0Python311"
set "PATH=%~dp0Python311;%~dp0Python311\\DLLs;%WINDIR%\\system32;%WINDIR%;%WINDIR%\\System32\\Wbem"
echo Starting Fusion Frame (FFrame) with Python 3.11...
echo Close the window or press Ctrl+C to stop.
"%~dp0Python311\\python.exe" -P "%~dp0FFrame.py"
'''
        try:
            with open(os.path.join(BASE_DIR, "run.bat"), "w", encoding="utf-8") as f:
                f.write(run_bat.strip())
            log("[OK] run.bat created")
        except Exception as e:
            log(f"[FAIL] Could not create run.bat: {e}")
            return

        tas_dir = os.path.join(BASE_DIR, "TheAnimeScripter")
        if not os.path.isdir(tas_dir):
            log("[..] Downloading TAS...")
            rc, out, err = _powershell("irm tas.nevermindnilas.dev/install.ps1 | iex")
            if rc != 0:
                log(f"[FAIL] TAS install error:\n{err}")
                return
            log("[OK] TAS installed")
        else:
            log("[..] TheAnimeScripter folder found, skipping TAS download")

        log("=== All dependencies installed ===")

    threading.Thread(target=task, daemon=True).start()


# ============================================================
# Create shortcut
# ============================================================

SHORTCUT_TEMPLATE = '''\
os.execute([[
start "" "{d}\\Python311\\python.exe" -P "{d}\\FFrame.py"
]])
'''


def _get_resolve_script_dir():
    base = os.environ.get("APPDATA" if sys.platform == "win32" else "HOME", "")
    if not base:
        return None
    if sys.platform == "win32":
        return os.path.join(base, "Blackmagic Design", "DaVinci Resolve",
                            "Support", "Fusion", "Scripts", "Utility")
    elif sys.platform == "darwin":
        return os.path.join(base, "Library", "Application Support",
                            "Blackmagic Design", "DaVinci Resolve",
                            "Fusion", "Scripts", "Utility")
    return os.path.join(base, ".local", "share",
                        "DaVinci Resolve", "Fusion", "Scripts", "Utility")


def run_create_shortcut():
    def task():
        log("=== Create Shortcut ===")
        lua_content = SHORTCUT_TEMPLATE.replace("{d}", BASE_DIR)
        lua_path = os.path.join(BASE_DIR, "FusionFrame.lua")
        try:
            with open(lua_path, "w", encoding="utf-8") as f:
                f.write(lua_content)
            log("[OK] Created FusionFrame.lua")
        except Exception as e:
            log(f"[FAIL] Could not create FusionFrame.lua: {e}")
            return

        resolve_dir = _get_resolve_script_dir()
        if resolve_dir and os.path.isdir(resolve_dir):
            try:
                shutil.copy2(lua_path, os.path.join(resolve_dir, "FusionFrame.lua"))
                log("[OK] Copied to Resolve Scripts folder")
            except Exception as e:
                log(f"[FAIL] Could not copy to Resolve: {e}")
        else:
            log(f"[..] Resolve Scripts folder not found at: {resolve_dir}")
            log("[..] Copy FusionFrame.lua manually to your Scripts folder")

        log("  Restart DaVinci Resolve then go to:")
        log("    Workspace > Scripts > FusionFrame")
        log("=== Done ===")

    threading.Thread(target=task, daemon=True).start()


# ============================================================
# Update Fusion Frame
# ============================================================

def run_update_fframe():
    def task():
        log("=== Update Fusion Frame ===")
        target = os.path.join(BASE_DIR, "FFrame.py")
        if os.path.exists(target):
            try:
                os.remove(target)
                log("[OK] Removed old FFrame.py")
            except Exception as e:
                log(f"[FAIL] Could not remove FFrame.py: {e}")
                return

        log("[..] Downloading latest Fusion Frame...")
        rc, _, _ = _powershell(
            "iwr -useb 'https://raw.githubusercontent.com/MisonTo20/Fusion-Frame/refs/heads/main/FFrame.py' -OutFile '{0}\\FFrame.py'".format(BASE_DIR))
        if rc != 0:
            log("[FAIL] Download failed")
            return
        log("[OK] Fusion Frame updated!")
        log("=== Done ===")

    threading.Thread(target=task, daemon=True).start()


# ============================================================
# Update TAS
# ============================================================

def _find_tas_dir():
    """Return the TAS installation directory, or None."""
    candidate = os.path.join(BASE_DIR, "TheAnimeScripter")
    if os.path.isdir(candidate):
        return candidate
    return None


def run_update_tas():
    def task():
        log("=== Update TAS ===")
        tas_dir = _find_tas_dir()
        if tas_dir:
            log(f"[..] Removing old TAS...")
            try:
                shutil.rmtree(tas_dir)
                log("[OK] Removed old TAS")
            except Exception as e:
                log(f"[FAIL] Could not remove TAS: {e}")
                return
        else:
            log("[..] No existing TAS folder found")

        log("[..] Downloading latest TAS...")
        rc, out, err = _powershell("irm tas.nevermindnilas.dev/install.ps1 | iex")
        if rc != 0:
            log(f"[FAIL] TAS install error:\n{err}")
            return
        log("[OK] TAS updated!")
        log("=== Done ===")

    threading.Thread(target=task, daemon=True).start()


# ============================================================
# Build UI
# ============================================================

dpg.create_context()
dpg.create_viewport(title="Fusion Frame Installer", width=640, height=520,
                    x_pos=200, y_pos=150, small_icon="", large_icon="")
dpg.setup_dearpygui()

with dpg.window(tag="main_win", label="Fusion Frame Installer",
                no_close=True, no_collapse=True):
    dpg.add_text("Fusion Frame Installer", tag="title_text")
    dpg.add_separator()
    dpg.add_spacer(height=4)

    with dpg.child_window(tag="log_child", height=-80, autosize_x=True, border=True):
        dpg.add_text("", tag="log_text", wrap=0)

    dpg.add_separator()
    dpg.add_spacer(height=4)

    with dpg.group(horizontal=True):
        dpg.add_button(label="Download dependencies", width=200, height=36,
                       callback=lambda: run_download_deps())
        dpg.add_button(label="Create shortcut", width=200, height=36,
                       callback=lambda: run_create_shortcut())

    with dpg.group(horizontal=True):
        dpg.add_button(label="Update Fusion Frame", width=200, height=36,
                       callback=lambda: run_update_fframe())
        dpg.add_button(label="Update TAS", width=200, height=36,
                       callback=lambda: run_update_tas())

dpg.set_primary_window("main_win", True)
dpg.show_viewport()

log("Welcome to the Fusion Frame Installer")
log("Select an option above to get started.")

while dpg.is_dearpygui_running():
    dpg.render_dearpygui_frame()

dpg.destroy_context()
