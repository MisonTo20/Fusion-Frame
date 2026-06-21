import io
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path

try:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout,
        QPushButton, QLabel, QProgressBar, QPlainTextEdit, QGroupBox,
    )
except Exception:
    # PySide6 isn't available in Resolve's Python yet. Install it the same
    # way install.bat does, then ask the user to re-run this script - the
    # Fusion console's embedded interpreter won't pick up a freshly
    # installed package without a soft restart (reopen the console / re-run
    # the script). On the next run this block is skipped entirely since the
    # import above will succeed.
    import ctypes as _ct
    MB_OK = 0

    def _find_real_python():
        """sys.executable inside Resolve's Fusion console is fuscript.exe,
        not a real Python - running pip through it silently no-ops (exit 0,
        nothing actually installed where the embedded interpreter's import
        machinery looks). Find the actual python.exe Resolve ships, same
        candidates install.bat checks."""
        candidates = [
            Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\python.exe"),
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
                / "Blackmagic Design" / "DaVinci Resolve" / "Support"
                / "Developer" / "Scripting" / "python.exe",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        # Fall back to whatever's on PATH, skipping fuscript.exe / WindowsApps stubs
        try:
            result = subprocess.run(
                ["where", "python"], capture_output=True, text=True, shell=True,
            )
            for line in result.stdout.strip().splitlines():
                p = line.strip()
                if "WindowsApps" not in p and "fuscript" not in p.lower() and Path(p).is_file():
                    return p
        except Exception:
            pass
        return None

    _py = _find_real_python()

    if not _py:
        _ct.windll.user32.MessageBoxW(
            0,
            "Could not locate DaVinci Resolve's python.exe.\n"
            "Run install.bat manually, or open Fusion -> Console (Py3) and run:\n"
            "import sys; print(sys.executable)\n"
            "then point this script at that path.",
            "FFrameInstaller", MB_OK,
        )
        sys.exit(1)

    _ct.windll.user32.MessageBoxW(
        0,
        f"PySide6 is not installed for this Python yet:\n{_py}\n\n"
        "Click OK to install it now (this can take a minute).",
        "FFrameInstaller", 1,
    )

    print(f"Using Python: {_py}")
    print("Installing PySide6 ...")
    subprocess.run(f'"{_py}" -m pip install --upgrade pip', shell=True, capture_output=True)
    code = subprocess.run(f'"{_py}" -m pip install PySide6', shell=True).returncode

    if code != 0:
        _ct.windll.user32.MessageBoxW(
            0,
            f"PySide6 install failed (exit {code}).\n"
            "See the Fusion console output above, or run install.bat manually.",
            "FFrameInstaller", MB_OK,
        )
        sys.exit(1)

    print("PySide6 installed OK.")
    _ct.windll.user32.MessageBoxW(
        0,
        "PySide6 installed successfully.\n\n"
        "Please drag-and-drop this script into the console again "
        "(or re-run it) to open the Fusion Frame installer.",
        "FFrameInstaller", MB_OK,
    )
    sys.exit(0)


def subprocess_flags():
    """Suppress the console window subprocesses would otherwise flash on Windows."""
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


try:
    PLUGIN_ROOT = Path(__file__).resolve().parent
except NameError:
    PLUGIN_ROOT = Path(sys.argv[0]).resolve().parent
SRC_DIR = PLUGIN_ROOT / "src"
BRIDGE_SRC = PLUGIN_ROOT / "bridge" / "FusionFrame.py"
TAS_DIR = PLUGIN_ROOT / "TheAnimeScripter"
TAS_PYTHON = TAS_DIR / "python.exe"
COMP_DIR = Path(os.environ["APPDATA"]) / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Comp"
BRIDGE_DEST = COMP_DIR / "FusionFrame.py"

GITHUB_ZIP_URL = "https://github.com/MisonTo20/Fusion-Frame/archive/refs/heads/main.zip"
GITHUB_BRIDGE_URL = "https://raw.githubusercontent.com/MisonTo20/Fusion-Frame/main/bridge/FusionFrame.py"
TAS_INSTALL_CMD = 'echo y | powershell -NoProfile -Command "iwr -useb https://tas.nevermindnilas.dev/install.ps1 | iex"'


def find_resolve_python():
    """Locate Resolve's real python.exe (not fuscript.exe)."""
    candidates = [
        Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\python.exe"),
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            / "Blackmagic Design" / "DaVinci Resolve" / "Support"
            / "Developer" / "Scripting" / "python.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    result = subprocess.run(
        ["where", "python"], capture_output=True, text=True, shell=True,
        creationflags=subprocess_flags(),
    )
    for line in result.stdout.strip().splitlines():
        p = line.strip()
        if "WindowsApps" not in p and "fuscript" not in p.lower() and Path(p).is_file():
            return p

    if "fuscript" not in sys.executable.lower() and Path(sys.executable).is_file():
        return sys.executable
    return None


def run_cmd(args, log_cb, cwd=None, timeout=None):
    """Run a command, streaming its output line-by-line to log_cb. Returns the exit code."""
    log_cb(f"$ {' '.join(str(a) for a in args)}")
    try:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd, creationflags=subprocess_flags(),
        )
        for line in proc.stdout:
            log_cb(line.rstrip())
        proc.wait(timeout=timeout)
        if proc.returncode != 0:
            log_cb(f"[exit code {proc.returncode}]")
        return proc.returncode
    except Exception as e:
        log_cb(f"Error: {e}")
        return -1


def remove_path(path, signals, label):
    """Remove a file or directory if it exists, logging the outcome."""
    if path.is_dir():
        signals.log.emit(f"Removing {path}...")
        shutil.rmtree(path)
        signals.log.emit(f"{label} removed")
    elif path.is_file():
        signals.log.emit(f"Removing {path}...")
        path.unlink()
        signals.log.emit(f"{label} removed")
    else:
        signals.log.emit(f"No {label} found")


class WorkerSignals(QObject):
    log = Signal(str)
    progress = Signal(int)
    status = Signal(str)
    done = Signal(bool, str)


def _install_fusion_frame(signals, resolve_py):
    signals.status.emit("Installing Fusion Frame...")
    signals.progress.emit(5)

    # Delete old src folder
    if SRC_DIR.is_dir():
        signals.log.emit(f"Removing old {SRC_DIR}...")
        shutil.rmtree(SRC_DIR)
        signals.log.emit("Old src removed")
    else:
        signals.log.emit("No existing src folder to remove")
    signals.progress.emit(10)

    # Download new src from GitHub
    signals.log.emit("Downloading Fusion Frame from GitHub...")
    signals.progress.emit(15)
    try:
        with urllib.request.urlopen(GITHUB_ZIP_URL, timeout=60) as resp:
            zip_data = resp.read()
    except Exception as e:
        signals.done.emit(False, f"Download failed: {e}")
        return
    signals.progress.emit(20)

    signals.log.emit("Extracting src/ folder...")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            prefix = next(
                (name for name in zf.namelist() if name.replace("\\", "/").endswith("/src/")),
                None,
            )
            if not prefix:
                signals.done.emit(False, "src/ folder not found in the downloaded archive")
                return
            for name in zf.namelist():
                if not name.startswith(prefix):
                    continue
                rel = Path(name).relative_to(Path(prefix))
                if not str(rel):
                    continue
                target = SRC_DIR / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if not name.endswith("/"):
                    target.write_bytes(zf.read(name))
    except Exception as e:
        signals.done.emit(False, f"Extraction failed: {e}")
        return
    signals.log.emit("src/ extracted OK")
    signals.progress.emit(30)

    # Install PySide6
    signals.log.emit(f"Using Python: {resolve_py}")
    signals.log.emit("")
    signals.log.emit("Installing PySide6...")
    signals.progress.emit(35)
    if run_cmd([resolve_py, "-m", "pip", "install", "--upgrade", "pip"], signals.log.emit) != 0:
        signals.log.emit("pip upgrade failed, continuing anyway...")
    if run_cmd([resolve_py, "-m", "pip", "install", "PySide6"], signals.log.emit) != 0:
        signals.done.emit(False, "PySide6 installation failed")
        return
    signals.log.emit("PySide6 installed OK")
    signals.progress.emit(50)

    # Verify plugin import
    signals.log.emit("")
    signals.log.emit("Verifying plugin import...")
    code = run_cmd([
        resolve_py, "-c",
        f"import sys; sys.path.insert(0, r'{SRC_DIR}'); import fusion_frame; print('Import OK:', fusion_frame.__file__)",
    ], signals.log.emit)
    if code != 0:
        signals.done.emit(False, "Plugin import verification failed")
        return
    signals.log.emit("Verified OK")
    signals.progress.emit(100)

    signals.done.emit(True, "Fusion Frame installed successfully")


def _install_tas(signals):
    if TAS_PYTHON.is_file():
        signals.log.emit("TheAnimeScripter already installed, skipping")
        signals.progress.emit(100)
        signals.done.emit(True, "TAS already installed")
        return

    signals.status.emit("Installing TheAnimeScripter...")
    signals.progress.emit(10)
    signals.log.emit("Downloading and running TAS installer...")
    signals.log.emit(f"$ {TAS_INSTALL_CMD}")

    try:
        proc = subprocess.Popen(
            TAS_INSTALL_CMD,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(PLUGIN_ROOT), shell=True,
            creationflags=subprocess_flags(),
        )
        for line in proc.stdout:
            signals.log.emit(line.rstrip())
        proc.wait()
        if proc.returncode != 0:
            signals.done.emit(False, "TAS installer failed")
            return
    except Exception as e:
        signals.done.emit(False, f"TAS installer error: {e}")
        return

    signals.progress.emit(80)
    if not TAS_PYTHON.is_file():
        signals.done.emit(False, "TAS was not found after installation")
        return

    signals.log.emit("TheAnimeScripter installed successfully")
    signals.progress.emit(100)
    signals.done.emit(True, "TAS installed successfully")


def _create_shortcut(signals):
    signals.status.emit("Updating bridge template...")
    signals.progress.emit(10)

    signals.log.emit("Downloading latest bridge script from GitHub...")
    try:
        with urllib.request.urlopen(GITHUB_BRIDGE_URL, timeout=30) as resp:
            bridge_content = resp.read().decode("utf-8")
    except Exception as e:
        signals.done.emit(False, f"Download failed: {e}")
        return
    signals.progress.emit(50)

    BRIDGE_SRC.parent.mkdir(parents=True, exist_ok=True)
    signals.progress.emit(70)

    try:
        import re
        bridge_content = re.sub(
            r'^PLUGIN_SRC = r".*?"',
            lambda m: f'PLUGIN_SRC = r"{SRC_DIR}"',
            bridge_content,
            count=1, flags=re.MULTILINE,
        )
        BRIDGE_SRC.write_text(bridge_content, encoding="utf-8")
        signals.log.emit(f"Written to {BRIDGE_SRC}")
    except Exception as e:
        signals.done.emit(False, f"Could not write bridge script: {e}")
        return
    signals.progress.emit(100)
    signals.done.emit(True, "Bridge template updated")


def _delete_all(signals):
    signals.status.emit("Deleting Fusion Frame and TAS...")
    signals.progress.emit(5)

    remove_path(SRC_DIR, signals, "src/")
    signals.progress.emit(20)

    remove_path(PLUGIN_ROOT / "bridge", signals, "bridge/")
    signals.progress.emit(35)

    remove_path(TAS_DIR, signals, "TAS directory")
    signals.progress.emit(50)

    try:
        remove_path(BRIDGE_DEST, signals, "bridge script at Resolve")
    except Exception as e:
        signals.log.emit(f"Could not remove bridge script: {e}")
    signals.progress.emit(65)

    resolve_py = find_resolve_python()
    if resolve_py:
        signals.log.emit("Uninstalling PySide6...")
        run_cmd([resolve_py, "-m", "pip", "uninstall", "PySide6", "-y"], signals.log.emit)
    else:
        signals.log.emit("Resolve Python not found, skipping PySide6 uninstall")
    signals.progress.emit(100)
    signals.done.emit(True, "Fusion Frame and TAS deleted")


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion Frame Installer")
        self.setFixedSize(640, 520)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        btn_group = QGroupBox("Actions")
        btn_layout = QVBoxLayout(btn_group)

        self.btn_ff = QPushButton("Install / Update Fusion Frame")
        self.btn_tas = QPushButton("Install / Update TAS")
        self.btn_shortcut = QPushButton("Create Resolve Script Shortcut")
        self.btn_delete = QPushButton("Delete Fusion Frame and TAS")
        self.buttons = (self.btn_ff, self.btn_tas, self.btn_shortcut, self.btn_delete)

        for btn in self.buttons:
            btn.setMinimumHeight(36)
            btn_layout.addWidget(btn)

        root.addWidget(btn_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        root.addWidget(self.status_label)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        root.addWidget(self.log_box, 1)

        self.btn_ff.clicked.connect(lambda: self._run(_install_fusion_frame, needs_resolve_py=True))
        self.btn_tas.clicked.connect(lambda: self._run(_install_tas))
        self.btn_shortcut.clicked.connect(lambda: self._run(_create_shortcut))
        self.btn_delete.clicked.connect(lambda: self._run(_delete_all))

    def _run(self, target, needs_resolve_py=False):
        self._set_buttons_enabled(False)
        self.log_box.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting...")

        signals = WorkerSignals()
        signals.log.connect(self._on_log)
        signals.progress.connect(self.progress_bar.setValue)
        signals.status.connect(self.status_label.setText)
        signals.done.connect(self._on_done)

        args = (signals,)
        if needs_resolve_py:
            resolve_py = find_resolve_python()
            if not resolve_py:
                self._on_log("Could not auto-detect Resolve's Python.")
                self._on_log("Make sure DaVinci Resolve is installed, or set the path manually.")
                self._on_done(False, "Resolve Python not found")
                return
            args = (signals, resolve_py)

        threading.Thread(target=target, args=args, daemon=True).start()

    def _on_log(self, msg):
        self.log_box.appendPlainText(msg)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def _on_done(self, ok, msg):
        self.status_label.setText(msg)
        self._set_buttons_enabled(True)
        if not ok:
            self.progress_bar.setValue(0)

    def _set_buttons_enabled(self, enabled):
        for btn in self.buttons:
            btn.setEnabled(enabled)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
