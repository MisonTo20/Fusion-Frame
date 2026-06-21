
import os
import subprocess
import threading
import time

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QCheckBox, QComboBox, QDoubleSpinBox,
    QSpinBox, QGroupBox, QScrollArea, QPlainTextEdit, QToolBox,
)

from fusion_frame import core


class _Signals(QObject):
    metadata_ready = Signal(dict)
    process_finished = Signal(object)
    import_done = Signal(str, bool)


class FusionFrameWindow(QMainWindow):

    def __init__(self, parent=None, resolve=None):
        super().__init__(parent)
        self.resolve = resolve
        self._clip_details = None
        self._log_lines = []

        self.setWindowTitle("Fusion Frame")
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowStaysOnTopHint
        )
        self.resize(640, 720)

        self.signals = _Signals()
        self.signals.metadata_ready.connect(self._on_metadata_ready)
        self.signals.process_finished.connect(self._on_process_finished)
        self.signals.import_done.connect(self._on_import_done)

        self.state = {
            "upscale": False, "upscale_method": "shufflecugan", "upscale_factor": 2,
            "custom_model": False, "custom_model_path": "",
            "interpolate": False, "interpolate_method": "rife4.6", "interpolate_factor": 2.0,
            "ensemble": False, "dynamic_scale": False, "slowmo": False,
            "static_step": False, "interpolate_first": True,
            "restore": False, "restore_method": "anime1080fixer", "stabilize": False,
            "dedup": False, "dedup_method": "ssim", "dedup_sens": 35,
            "segment": False, "segment_method": "anime",
            "depth": False, "depth_method": "small_v2", "depth_quality": "low", "depth_norm": False,
            "obj_detect": False, "obj_detect_method": "yolov9_small-directml",
            "autoclip": False, "autoclip_sens": 50.0,
            "resize": False, "resize_factor": 2.0, "output_scale": "",
            "encode_method": "x264", "custom_encoder": "",
            "half": True, "static": False, "compile_mode": "default",
            "download_req": "none", "cleanup": False, "bit_depth": "8bit",
            "benchmark": False, "preview": False,
            "ae_enable": False, "ae_host": "127.0.0.1:PORT",
            "add_red": True, "import_on_top": True,
        }

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ----- top row: grab clip + source path -----
        top_row = QHBoxLayout()
        grab_btn = QPushButton("Grab Clip")
        grab_btn.clicked.connect(self._load_from_resolve)
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Source path")
        self.source_input.textChanged.connect(lambda t: self.state.update({"source_path": t}))
        top_row.addWidget(grab_btn)
        top_row.addWidget(self.source_input)
        root.addLayout(top_row)

        # ----- scrollable settings area -----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._sections = QVBoxLayout(container)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        self._sections.addWidget(self._build_upscale_group())
        self._sections.addWidget(self._build_interpolate_group())
        self._sections.addWidget(self._build_restore_group())
        self._sections.addWidget(self._build_dedup_group())
        self._sections.addWidget(self._build_segment_group())
        self._sections.addWidget(self._build_depth_group())
        self._sections.addWidget(self._build_objdetect_group())
        self._sections.addWidget(self._build_autoclip_group())
        self._sections.addWidget(self._build_export_group())
        self._sections.addWidget(self._build_advanced_group())
        self._sections.addStretch(1)

        # ----- run row -----
        run_row = QHBoxLayout()
        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._run_process)
        self.status_label = QLabel("Ready")
        run_row.addWidget(run_btn)
        run_row.addWidget(self.status_label, 1)
        root.addLayout(run_row)

        # ----- log -----
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(110)
        root.addWidget(self.log_box)

    def _checkbox(self, label, key, default=False):
        cb = QCheckBox(label)
        cb.setChecked(default)
        cb.toggled.connect(lambda v: self.state.update({key: v}))
        return cb

    def _combo(self, key, items, default):
        cb = QComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        cb.currentTextChanged.connect(lambda v: self.state.update({key: v}))
        return cb

    def _int_spin(self, key, default, lo, hi):
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(default)
        sb.valueChanged.connect(lambda v: self.state.update({key: v}))
        return sb

    def _float_spin(self, key, default, lo, hi, step=0.1):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setSingleStep(step)
        sb.setValue(default)
        sb.valueChanged.connect(lambda v: self.state.update({key: v}))
        return sb

    def _line_edit(self, key, default=""):
        le = QLineEdit()
        le.setText(default)
        le.textChanged.connect(lambda v: self.state.update({key: v}))
        return le

    # ----- group builders -----

    def _build_upscale_group(self):
        g = QGroupBox("Upscale")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"upscale": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Method"), 0, 0)
        lay.addWidget(self._combo("upscale_method",
            ["shufflecugan", "adore", "fallin_soft", "fallin_strong", "span",
             "open-proteus", "aniscale2", "rtmosr", "saryn", "gauss", "animesr"],
            "shufflecugan"), 0, 1)
        lay.addWidget(QLabel("Factor"), 1, 0)
        lay.addWidget(self._int_spin("upscale_factor", 2, 2, 4), 1, 1)
        custom_cb = self._checkbox("Custom Model", "custom_model")
        lay.addWidget(custom_cb, 2, 0)
        lay.addWidget(self._line_edit("custom_model_path"), 2, 1)
        return g

    def _build_interpolate_group(self):
        g = QGroupBox("Interpolate")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"interpolate": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Method"), 0, 0)
        lay.addWidget(self._combo("interpolate_method",
            ["rife4.6", "rife4.22", "rife4.25", "rife4.25-lite", "rife4.25-heavy", "gmfss"],
            "rife4.6"), 0, 1)
        lay.addWidget(QLabel("Factor"), 1, 0)
        lay.addWidget(self._float_spin("interpolate_factor", 2.0, 1.0, 4.0, 0.1), 1, 1)
        lay.addWidget(self._checkbox("Ensemble", "ensemble"), 2, 0)
        lay.addWidget(self._checkbox("Dynamic Scale", "dynamic_scale"), 2, 1)
        lay.addWidget(self._checkbox("Slow Motion", "slowmo"), 3, 0)
        lay.addWidget(self._checkbox("Static Step", "static_step"), 3, 1)
        lay.addWidget(self._checkbox("Interpolate First", "interpolate_first", True), 4, 0)
        return g

    def _build_restore_group(self):
        g = QGroupBox("Restore")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"restore": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Method"), 0, 0)
        lay.addWidget(self._combo("restore_method",
            ["scunet", "nafnet", "dpir", "real-plksr", "anime1080fixer", "fastlinedarken",
             "autocas", "gater3", "deh264_real", "deh264_span", "hurrdeblur"],
            "anime1080fixer"), 0, 1)
        lay.addWidget(self._checkbox("Stabilize", "stabilize"), 1, 0)
        return g

    def _build_dedup_group(self):
        g = QGroupBox("Deduplication")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"dedup": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Method"), 0, 0)
        lay.addWidget(self._combo("dedup_method",
            ["ssim", "ssim-cuda", "mse", "mse-cuda", "flownets", "vmaf", "vmaf-cuda"],
            "ssim"), 0, 1)
        lay.addWidget(QLabel("Sensitivity"), 1, 0)
        lay.addWidget(self._int_spin("dedup_sens", 35, 0, 100), 1, 1)
        return g

    def _build_segment_group(self):
        g = QGroupBox("Segmentation")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"segment": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Method"), 0, 0)
        lay.addWidget(self._combo("segment_method", ["anime", "anime-tensorrt"], "anime"), 0, 1)
        return g

    def _build_depth_group(self):
        g = QGroupBox("Depth")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"depth": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Method"), 0, 0)
        lay.addWidget(self._combo("depth_method",
            ["small_v2", "base_v2", "large_v2", "giant_v2", "distill_small_v2",
             "distill_base_v2", "distill_large_v2", "og_small_v2", "og_base_v2",
             "og_large_v2", "og_large_v3"], "small_v2"), 0, 1)
        lay.addWidget(QLabel("Quality"), 1, 0)
        lay.addWidget(self._combo("depth_quality", ["low", "medium", "high"], "low"), 1, 1)
        lay.addWidget(self._checkbox("Depth Norm", "depth_norm"), 2, 0)
        return g

    def _build_objdetect_group(self):
        g = QGroupBox("Object Detection")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"obj_detect": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Method"), 0, 0)
        lay.addWidget(self._combo("obj_detect_method",
            ["yolov9_small-directml", "yolov9_medium-directml", "yolov9_large-directml"],
            "yolov9_small-directml"), 0, 1)
        return g

    def _build_autoclip_group(self):
        g = QGroupBox("Auto Clip Detection")
        g.setCheckable(True)
        g.setChecked(False)
        g.toggled.connect(lambda v: self.state.update({"autoclip": v}))
        lay = QGridLayout(g)
        lay.addWidget(QLabel("Sensitivity"), 0, 0)
        lay.addWidget(self._float_spin("autoclip_sens", 50.0, 0.0, 100.0, 1.0), 0, 1)
        return g

    def _build_export_group(self):
        g = QGroupBox("Export && Encoding")
        lay = QGridLayout(g)
        lay.addWidget(self._checkbox("Resize", "resize"), 0, 0)
        lay.addWidget(self._float_spin("resize_factor", 2.0, 0.1, 10.0, 0.1), 0, 1)
        lay.addWidget(QLabel("Output Scale (e.g. 3840x2160)"), 1, 0)
        lay.addWidget(self._line_edit("output_scale"), 1, 1)
        lay.addWidget(QLabel("Encode Method"), 2, 0)
        lay.addWidget(self._combo("encode_method",
            ["x264", "x264_animation", "x264_animation_10bit", "x264_10bit", "x265",
             "x265_10bit", "av1", "nvenc_h264", "nvenc_h265", "nvenc_h265_10bit",
             "nvenc_av1", "qsv_h264", "qsv_h265", "qsv_h265_10bit", "qsv_vp9",
             "h264_amf", "hevc_amf", "hevc_amf_10bit", "slow_x264", "slow_nvenc_h264",
             "slow_x265", "slow_nvenc_h265", "slow_av1", "slow_nvenc_av1", "prores",
             "prores_segment", "gif", "png", "vp9", "lossless", "lossless_nvenc"],
            "x264"), 2, 1)
        lay.addWidget(QLabel("Custom Encoder"), 3, 0)
        lay.addWidget(self._line_edit("custom_encoder"), 3, 1)
        return g

    def _build_advanced_group(self):
        g = QGroupBox("Advanced")
        lay = QGridLayout(g)
        lay.addWidget(self._checkbox("Half precision", "half", True), 0, 0)
        lay.addWidget(self._checkbox("Static mode", "static"), 0, 1)
        lay.addWidget(QLabel("Compile mode"), 1, 0)
        lay.addWidget(self._combo("compile_mode", ["default", "max", "max-graphs"], "default"), 1, 1)
        lay.addWidget(QLabel("Download reqs"), 2, 0)
        lay.addWidget(self._combo("download_req",
            ["none", "windows-cuda", "windows-lite", "linux-cuda", "linux-lite"], "none"), 2, 1)
        lay.addWidget(self._checkbox("Cleanup", "cleanup"), 3, 0)
        lay.addWidget(QLabel("Bit depth"), 3, 1)
        lay.addWidget(self._combo("bit_depth", ["8bit", "16bit"], "8bit"), 4, 1)
        lay.addWidget(self._checkbox("Benchmark", "benchmark"), 5, 0)
        lay.addWidget(self._checkbox("Preview", "preview"), 5, 1)
        lay.addWidget(self._checkbox("Enable AE", "ae_enable"), 6, 0)
        lay.addWidget(QLabel("AE Host"), 7, 0)
        lay.addWidget(self._line_edit("ae_host", "127.0.0.1:PORT"), 7, 1)
        return g

    # ------------------------------------------------------------------
    # Logging / status
    # ------------------------------------------------------------------

    def _log(self, msg):
        ts = time.strftime("[%H:%M:%S]")
        self._log_lines.append(f"{ts} {msg}")
        self.log_box.setPlainText("\n".join(self._log_lines[-200:]))
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def _set_status(self, msg):
        self.status_label.setText(msg)

    # ------------------------------------------------------------------
    # Resolve interaction
    # ------------------------------------------------------------------

    def _load_from_resolve(self):
        if not self.resolve:
            self._log("No connection to Resolve. Run this plugin from Scripts > Comp.")
            return
        threading.Thread(target=self._fetch_metadata, daemon=True).start()

    def _fetch_metadata(self):
        meta = core.get_current_clip_metadata(self.resolve)
        self.signals.metadata_ready.emit(meta)

    def _on_metadata_ready(self, meta):
        if meta.get("success"):
            self._clip_details = {
                "clip_name": meta["clip_name"],
                "start_frame": meta["start_frame"],
                "duration": meta["duration"],
            }
            self.state["source_path"] = meta.get("source_path", "")
            self.source_input.setText(meta.get("source_path", ""))
            self._log(f"Grabbed clip: {meta.get('clip_name')} from Resolve")
        else:
            self._log(f"Failed to grab clip: {meta.get('error')}")

    # ------------------------------------------------------------------
    # Render command construction (unchanged from original)
    # ------------------------------------------------------------------

    def _build_command(self):
        s = self.state
        args = []
        ip = s.get("inpoint", 0)
        op = s.get("outpoint", 0)
        if ip and float(ip) > 0:
            args.extend(["--inpoint", str(ip)])
        if op and float(op) > 0:
            args.extend(["--outpoint", str(op)])
        if s.get("benchmark"):
            args.append("--benchmark")
        if s.get("preview"):
            args.append("--preview")
        if s.get("ae_enable"):
            h = s.get("ae_host")
            if h:
                args.extend(["--ae", h])
        if s.get("upscale"):
            args.append("--upscale")
            args.extend(["--upscale_factor", str(s["upscale_factor"])])
            args.extend(["--upscale_method", s["upscale_method"]])
            if s.get("custom_model") and s.get("custom_model_path"):
                args.extend(["--custom_model", s["custom_model_path"]])
        if s.get("interpolate"):
            args.append("--interpolate")
            args.extend(["--interpolate_factor", str(s["interpolate_factor"])])
            args.extend(["--interpolate_method", s["interpolate_method"]])
            if s.get("ensemble"):
                args.append("--ensemble")
            if s.get("dynamic_scale"):
                args.append("--dynamic_scale")
            if s.get("slowmo"):
                args.append("--slowmo")
            if s.get("static_step"):
                args.append("--static_step")
            if not s.get("interpolate_first", True):
                args.extend(["--interpolate_first", "False"])
        if s.get("restore"):
            args.append("--restore")
            rm = s.get("restore_method")
            if rm:
                args.extend(["--restore_method", rm])
            if s.get("stabilize"):
                args.append("--stabilize")
        if s.get("dedup"):
            args.append("--dedup")
            args.extend(["--dedup_method", s["dedup_method"]])
            args.extend(["--dedup_sens", str(s["dedup_sens"])])
        if s.get("segment"):
            args.append("--segment")
            args.extend(["--segment_method", s["segment_method"]])
        if s.get("depth"):
            args.append("--depth")
            args.extend(["--depth_method", s["depth_method"]])
            args.extend(["--depth_quality", s["depth_quality"]])
            if s.get("depth_norm"):
                args.append("--depth_norm")
        if s.get("obj_detect"):
            args.append("--obj_detect")
            args.extend(["--obj_detect_method", s["obj_detect_method"]])
        if s.get("autoclip"):
            args.append("--autoclip")
            args.extend(["--autoclip_sens", str(s["autoclip_sens"])])
        if s.get("resize"):
            args.append("--resize")
            args.extend(["--resize_factor", str(s["resize_factor"])])
        out_scale = s.get("output_scale")
        if out_scale:
            args.extend(["--output_scale", out_scale])
        enc = s.get("encode_method")
        if enc:
            args.extend(["--encode_method", enc])
        ce = s.get("custom_encoder")
        if ce:
            args.extend(["--custom_encoder", ce])
        if s.get("half", True) is False:
            args.extend(["--half", "False"])
        if s.get("static"):
            args.append("--static")
        cm = s.get("compile_mode")
        if cm and cm != "default":
            args.extend(["--compile_mode", cm])
        dl = s.get("download_req")
        if dl and dl != "none":
            args.extend(["--download_requirements", dl])
        if s.get("cleanup"):
            args.append("--cleanup")
        bd = s.get("bit_depth")
        if bd:
            args.extend(["--bit_depth", bd])
        return args

    # ------------------------------------------------------------------
    # Run / import pipeline (subprocess render, unchanged in spirit)
    # ------------------------------------------------------------------

    def _run_process(self):
        src = self.state.get("source_path")
        if not src:
            self._set_status("Error: No source path")
            self._log("Error: No source path")
            return

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        tas_dir = os.path.join(plugin_root, "TheAnimeScripter")

        if not os.path.isdir(tas_dir):
            self._log(f"TAS directory not found: {tas_dir}")
            self._set_status("Error: TAS not found")
            return

        python_exe = os.path.join(tas_dir, "python.exe")
        if not os.path.isfile(python_exe):
            self._log(f"TAS Python not found: {python_exe}")
            self._set_status("Error: TAS Python not found")
            return

        base, ext = os.path.splitext(os.path.basename(src))
        out_path = os.path.join(os.path.dirname(src), f"{base}_FusionFrame.mp4")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        cmd_args = self._build_command()
        args_str = " ".join(cmd_args)
        self._log(f'[Run] python.exe main.py --input "{src}" --output "{out_path}" {args_str}')

        try:
            popen_kwargs = {}
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            proc = subprocess.Popen(
                [python_exe, os.path.join(tas_dir, "main.py"),
                 "--input", src, "--output", out_path] + cmd_args,
                cwd=tas_dir, **popen_kwargs,
            )
            self._set_status("TAS running...")
            threading.Thread(target=self._monitor_process, args=(proc, out_path), daemon=True).start()
        except Exception as e:
            self._set_status(f"Run failed: {e}")
            self._log(f"Run failed: {e}")

    def _monitor_process(self, proc, out_path):
        proc.wait()
        time.sleep(1)
        if proc.returncode != 0:
            self.signals.process_finished.emit(
                {"ok": False, "path": "", "error": f"TAS exited with code {proc.returncode}"}
            )
        else:
            self.signals.process_finished.emit({"ok": True, "path": out_path, "error": ""})

    def _on_process_finished(self, result):
        if not result["ok"]:
            self._log(f"[TAS] {result['error']}")
            self._set_status("TAS failed")
            return

        out_path = result["path"]
        self._log("[Run] TAS finished, importing rendered clip")

        if not self._clip_details:
            self._log("[Import] No clip details cached (grab a clip first)")
            return

        if not os.path.isfile(out_path):
            self._log(f"[Import] Output file not found: {out_path}")
            return

        latest_name = os.path.basename(out_path)
        threading.Thread(target=self._import_clip, args=(out_path, latest_name), daemon=True).start()

    def _import_clip(self, fp, latest_name):
        try:
            err = core.import_and_align_clip(
                self.resolve, fp, self._clip_details,
                add_red=self.state["add_red"], import_on_top=self.state["import_on_top"],
            )
            if err:
                self.signals.import_done.emit(f"[Import] Failed to import rendered clip: {err}", False)
            else:
                self.signals.import_done.emit(f"[Import] Rendered clip '{latest_name}' imported successfully.", True)
        except Exception as e:
            self.signals.import_done.emit(f"[Import] Failed to import rendered clip: {e}", False)

    def _on_import_done(self, msg, ok):
        self._log(msg)
