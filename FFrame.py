import os
import sys as _sys
import subprocess
import threading
import time
import json as _json

RESOLVE_MODULES = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"

# ==============================================================================
# DaVinci Resolve scripting module loader
# ==============================================================================

def _import_dvr():
    try:
        import DaVinciResolveScript as dvr_script
        return dvr_script
    except ImportError:
        pass
    if os.path.exists(RESOLVE_MODULES) and RESOLVE_MODULES not in _sys.path:
        _sys.path.append(RESOLVE_MODULES)
    try:
        import DaVinciResolveScript as dvr_script
        return dvr_script
    except ImportError:
        return None

# ==============================================================================
# Direct (same-process) Resolve API implementations
# ==============================================================================

def _direct_get_resolve():
    dvr_script = _import_dvr()
    if not dvr_script:
        return None, "DaVinci Resolve scripting module not found"
    resolve_obj = dvr_script.scriptapp("Resolve")
    if not resolve_obj:
        return None, "Could not connect to Resolve (is it running?)"
    return resolve_obj, None

def _direct_get_current_clip_metadata():
    try:
        resolve_obj, err = _direct_get_resolve()
        if err:
            return {"success": False, "error": err}
        pm = resolve_obj.GetProjectManager()
        if not pm:
            return {"success": False, "error": "Could not access Project Manager"}
        project = pm.GetCurrentProject()
        if not project:
            return {"success": False, "error": "No project open"}
        timeline = project.GetCurrentTimeline()
        if not timeline:
            return {"success": False, "error": "No active timeline"}
        item = timeline.GetCurrentVideoItem()
        if not item:
            return {"success": False, "error": "No video clip under playhead"}
        clip_name = item.GetName() or "Unnamed"
        start = item.GetStart()
        duration = item.GetDuration()
        left_offset = item.GetLeftOffset()
        try:
            framerate = float(project.GetSetting("timelineFrameRate") or 24.0)
        except ValueError:
            framerate = 24.0
        mp_item = item.GetMediaPoolItem()
        source_path = ""
        if mp_item:
            source_path = mp_item.GetClipProperty("File Path") or ""
        if not source_path:
            return {"success": False, "error": f"Clip '{clip_name}' has no source file path"}
        return {
            "success": True,
            "clip_obj": item,
            "clip_name": clip_name,
            "source_path": source_path,
            "start_frame": int(start or 0),
            "duration": int(duration or 0),
            "left_offset": int(left_offset or 0),
            "timeline_framerate": framerate,
        }
    except Exception as e:
        return {"success": False, "error": f"Resolve API error: {e}"}

def _direct_get_project_path():
    try:
        resolve_obj, err = _direct_get_resolve()
        if err:
            return None
        pm = resolve_obj.GetProjectManager()
        if not pm:
            return None
        project = pm.GetCurrentProject()
        if not project:
            return None
        return project.GetProjectPath()
    except Exception:
        return None

def _find_item_track(timeline, name, start, duration):
    count = timeline.GetTrackCount("video")
    for i in range(1, count + 1):
        items = timeline.GetItemListInTrack("video", i)
        if items:
            for item in items:
                if item.GetName() == name and item.GetStart() == start and item.GetDuration() == duration:
                    return i
    return None

def _direct_import_and_align_clip(file_path, clip_details, **kwargs):
    resolve_obj, err = _direct_get_resolve()
    if err or not resolve_obj:
        return f"Resolve connection error: {err or 'Unknown'}"
    pm = resolve_obj.GetProjectManager()
    if not pm:
        return "Could not access Project Manager"
    project = pm.GetCurrentProject()
    if not project:
        return "No project open"
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return "No active timeline"

    mp = project.GetMediaPool()
    if not mp:
        return "Could not access Media Pool"
    try:
        imported_items = mp.ImportMedia([file_path])
    except Exception as e:
        return f"Media import failed: {e}"
    if not imported_items:
        return "Media import returned no items"
    media_item = imported_items[0]

    current_track = _find_item_track(timeline, clip_details.get("clip_name", ""),
                                    clip_details.get("start_frame", 0),
                                    clip_details.get("duration", 0))
    if current_track is None:
        return "Could not locate current clip on timeline"

    import_on_top = kwargs.get('import_on_top', True)
    if import_on_top:
        target_track = current_track - 1
        if target_track < 1:
            timeline.AddTrack("video")
            target_track = 1
    else:
        target_track = current_track + 1
        while timeline.GetTrackCount("video") < target_track:
            timeline.AddTrack("video")

    append_result = mp.AppendToTimeline([media_item])
    if not append_result:
        return "Failed to append imported clip to timeline"

    new_item = append_result[0] if isinstance(append_result, (list, tuple)) else None
    if not new_item:
        items = timeline.GetItemListInTrack("video", target_track)
        new_item = items[-1] if items else None
    if not new_item:
        return "Could not retrieve the imported clip from timeline"

    try:
        new_item.SetStart(clip_details.get("start_frame", 0))
        new_item.SetDuration(clip_details.get("duration", 0))
        if target_track != current_track:
            timeline.MoveClip(new_item, "video", target_track)
        if kwargs.get('add_red', True):
            try:
                timeline.SetTrackColor("video", target_track, "Red")
            except Exception:
                pass
        try:
            new_item.SetClipProperty("UserLabel", "imported_red")
        except Exception:
            pass
    except Exception as e:
        return f"Failed to align imported clip: {e}"
    return None

# ==============================================================================
# Subprocess bridge helpers (for Python != 3.11)
# ==============================================================================

_PYTHON311 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Python311", "python.exe")


def _call_py311(command, arg=None):
    try:
        args = [_PYTHON311, __file__, command]
        if arg is not None:
            args.append(_json.dumps(arg))
        py311_dir = os.path.dirname(_PYTHON311)
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, cwd=py311_dir)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip() or "subprocess failed"}
        return _json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Resolve connection timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _use_subprocess():
    if getattr(_use_subprocess, "_cached", None) is None:
        if _sys.version_info[:2] != (3, 11):
            _use_subprocess._cached = True
        else:
            try:
                result = _import_dvr()
                _use_subprocess._cached = not bool(result)
            except Exception:
                _use_subprocess._cached = False
    return _use_subprocess._cached


# ==============================================================================
# Public API: auto-route between subprocess bridge and direct implementations
# ==============================================================================

def get_resolve():
    if _use_subprocess():
        return None, "use subprocess"
    return _direct_get_resolve()


def get_current_clip_metadata():
    if _use_subprocess():
        return _call_py311("get_current_clip_metadata")
    return _direct_get_current_clip_metadata()


def get_project_path():
    if _use_subprocess():
        result = _call_py311("get_project_path")
        return result if isinstance(result, str) else None
    return _direct_get_project_path()


def import_clip_above_current(file_path, clip_details):
    return import_and_align_clip(file_path, clip_details)


def import_and_align_clip(file_path, clip_details, **kwargs):
    if _use_subprocess():
        result = _call_py311("import_clip_to_timeline", {"file_path": file_path, "clip_details": clip_details})
        return result.get("error")
    return _direct_import_and_align_clip(file_path, clip_details, **kwargs)


# ==============================================================================
# GUI application
# ==============================================================================

def main():
    import dearpygui.dearpygui as dpg

    log_lines = []
    state = {
        "source_path": "",
        "inpoint": 0.0,
        "outpoint": 0.0,
        "half": True,
        "static": False,
        "compile_mode": "default",
        "download_req": "none",
        "cleanup": False,
        "bit_depth": "8bit",
        "benchmark": False,
        "preview": False,
        "ae_enable": False,
        "ae_host": "127.0.0.1:PORT",
        "upscale": False,
        "upscale_method": "shufflecugan",
        "upscale_factor": 2,
        "custom_model": False,
        "custom_model_path": "",
        "interpolate": False,
        "interpolate_method": "rife4.6",
        "interpolate_factor": 2.0,
        "ensemble": False,
        "dynamic_scale": False,
        "slowmo": False,
        "static_step": False,
        "interpolate_first": True,
        "restore": False,
        "restore_method": "anime1080fixer",
        "stabilize": False,
        "dedup": False,
        "dedup_method": "ssim",
        "dedup_sens": 35,
        "segment": False,
        "segment_method": "anime",
        "depth": False,
        "depth_method": "small_v2",
        "depth_quality": "low",
        "depth_norm": False,
        "obj_detect": False,
        "obj_detect_method": "yolov9_small-directml",
        "autoclip": False,
        "autoclip_sens": 50.0,
        "resize": False,
        "resize_factor": 2.0,
        "output_scale": "",
        "encode_method": "x264",
        "custom_encoder": "",
        "add_red": True,
        "import_on_top": True,
        "status": "Ready",
    }

    _metadata_result = None
    _clip_details = None

    def log(msg):
        nonlocal log_lines
        ts = time.strftime("[%H:%M:%S]")
        log_lines.append(f"{ts} {msg}")
        dpg.set_value("log_text", "\n".join(log_lines[-200:]))

    def update_status(msg):
        state["status"] = msg
        dpg.set_value("status_text", msg)

    def refresh_metadata():
        meta = get_current_clip_metadata()
        nonlocal _metadata_result
        _metadata_result = meta

    def poll_metadata():
        nonlocal _metadata_result, _clip_details
        meta = _metadata_result
        if meta is None:
            return
        _metadata_result = None
        if meta.get("success"):
            _clip_details = {
                "clip_name": meta["clip_name"],
                "start_frame": meta["start_frame"],
                "duration": meta["duration"],
            }
            state["source_path"] = meta.get("source_path", "")
            dpg.set_value("clip_label", f"Clip: {meta.get('clip_name')} | Start: {meta.get('start_frame')} | Duration: {meta.get('duration')}")
            dpg.set_value("source_input", meta.get("source_path", ""))
            log(f"Grabbed clip: {meta.get('clip_name')} from Resolve")
        else:
            dpg.set_value("clip_label", f"Error: {meta.get('error')}")
            log(f"Failed to grab clip: {meta.get('error')}")

    def load_from_resolve():
        threading.Thread(target=refresh_metadata, daemon=True).start()

    def build_command():
        args = []
        ip = state.get("inpoint", 0)
        op = state.get("outpoint", 0)
        if ip and float(ip) > 0:
            args.extend(["--inpoint", str(ip)])
        if op and float(op) > 0:
            args.extend(["--outpoint", str(op)])
        if state.get("benchmark"): args.append("--benchmark")
        if state.get("preview"): args.append("--preview")
        if state.get("ae_enable"):
            h = state.get("ae_host")
            if h: args.extend(["--ae", h])
        if state.get("upscale"):
            args.append("--upscale")
            args.extend(["--upscale_factor", str(state["upscale_factor"])])
            args.extend(["--upscale_method", state["upscale_method"]])
            if state.get("custom_model") and state.get("custom_model_path"):
                args.extend(["--custom_model", state["custom_model_path"]])
        if state.get("interpolate"):
            args.append("--interpolate")
            args.extend(["--interpolate_factor", str(state["interpolate_factor"])])
            args.extend(["--interpolate_method", state["interpolate_method"]])
            if state.get("ensemble"): args.append("--ensemble")
            if state.get("dynamic_scale"): args.append("--dynamic_scale")
            if state.get("slowmo"): args.append("--slowmo")
            if state.get("static_step"): args.append("--static_step")
            if not state.get("interpolate_first", True): args.extend(["--interpolate_first", "False"])
        if state.get("restore"):
            args.append("--restore")
            rm = state.get("restore_method")
            if rm: args.extend(["--restore_method", rm])
            if state.get("stabilize"): args.append("--stabilize")
        if state.get("dedup"):
            args.append("--dedup")
            args.extend(["--dedup_method", state["dedup_method"]])
            args.extend(["--dedup_sens", str(state["dedup_sens"])])
        if state.get("segment"):
            args.append("--segment")
            args.extend(["--segment_method", state["segment_method"]])
        if state.get("depth"):
            args.append("--depth")
            args.extend(["--depth_method", state["depth_method"]])
            args.extend(["--depth_quality", state["depth_quality"]])
            if state.get("depth_norm"): args.append("--depth_norm")
        if state.get("obj_detect"):
            args.append("--obj_detect")
            args.extend(["--obj_detect_method", state["obj_detect_method"]])
        if state.get("autoclip"):
            args.append("--autoclip")
            args.extend(["--autoclip_sens", str(state["autoclip_sens"])])
        if state.get("resize"):
            args.append("--resize")
            args.extend(["--resize_factor", str(state["resize_factor"])])
        os_ = state.get("output_scale")
        if os_: args.extend(["--output_scale", os_])
        enc = state.get("encode_method")
        if enc: args.extend(["--encode_method", enc])
        ce = state.get("custom_encoder")
        if ce: args.extend(["--custom_encoder", ce])
        if state.get("half"): args.append("--half")
        if state.get("static"): args.append("--static")
        cm = state.get("compile_mode")
        if cm and cm != "default": args.extend(["--compile_mode", cm])
        dl = state.get("download_req")
        if dl and dl != "none": args.extend(["--download_requirements", dl])
        if state.get("cleanup"): args.append("--cleanup")
        bd = state.get("bit_depth")
        if bd: args.extend(["--bit_depth", bd])
        return args

    def run_process():
        src = state.get("source_path")
        if not src:
            update_status("Error: No source path")
            log("Error: No source path")
            return
        tas_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TheAnimeScripter")
        out_dir = os.path.join(os.path.dirname(src), "Framer exports")
        os.makedirs(out_dir, exist_ok=True)
        cmd_args = build_command()
        args_str = " ".join(cmd_args)
        log(f"[Run] python.exe main.py --input \"{src}\" --output \"{out_dir}\" {args_str}")
        try:
            proc = subprocess.Popen(
                [os.path.join(tas_dir, "python.exe"), os.path.join(tas_dir, "main.py"),
                 "--input", src, "--output", out_dir] + cmd_args,
                cwd=tas_dir, creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            update_status(f"Running in '{tas_dir}'...")
            threading.Thread(target=_monitor_process, args=(proc, out_dir), daemon=True).start()
        except Exception as e:
            update_status(f"Run failed: {e}")
            log(f"Run failed: {e}")

    def _monitor_process(proc, out_dir):
        proc.wait()
        log("[Run] Process finished, importing rendered clip")
        time.sleep(1)
        _after_export(out_dir)

    def _after_export(out_dir):
        nonlocal _clip_details
        if not _clip_details:
            log("[Import] No clip details cached (grab a clip first)"); return
        try:
            files = [f for f in os.listdir(out_dir) if os.path.isfile(os.path.join(out_dir, f))]
            if not files:
                log("[Import] No output files found."); return
            latest = max(files, key=lambda f: os.path.getmtime(os.path.join(out_dir, f)))
            fp = os.path.join(out_dir, latest)
        except Exception as e:
            log(f"[Import] Error locating file: {e}"); return
        try:
            import_and_align_clip(fp, _clip_details, add_red=state["add_red"], import_on_top=state["import_on_top"])
            log(f"[Import] Rendered clip '{latest}' imported successfully.")
        except Exception as e:
            log(f"[Import] Failed to import rendered clip: {e}")

    # ========== BUILD UI ==========
    dpg.create_context()
    dpg.create_viewport(title="Fusion Frame (FFrame)", width=620, height=640, x_pos=100, y_pos=50)
    dpg.setup_dearpygui()

    with dpg.window(tag="main_win", label="Fusion Frame (FFrame)", no_close=True, no_collapse=True):
        with dpg.group(horizontal=True):
            dpg.add_button(label="Grab Clip", callback=lambda: load_from_resolve())
            dpg.add_text(tag="clip_label", default_value="Click 'Grab Clip' to connect...", color=[180, 180, 180])
            dpg.add_input_text(tag="source_input", readonly=True, default_value="", width=-1)

        with dpg.child_window(height=-60, autosize_x=True, no_scrollbar=True):
            with dpg.collapsing_header(label="Upscale", default_open=False):
                dpg.add_checkbox(tag="upscale", label="Enable Upscale", default_value=False, callback=lambda s, a: state.update({"upscale": a}))
                dpg.add_combo(tag="upscale_method", label="Method", items=["shufflecugan","adore","fallin_soft","fallin_strong","span","open-proteus","aniscale2","rtmosr","saryn","gauss","animesr"], default_value="shufflecugan", callback=lambda s, a: state.update({"upscale_method": a}))
                dpg.add_drag_int(tag="upscale_factor", label="Factor", default_value=2, min_value=2, max_value=4, callback=lambda s, a: state.update({"upscale_factor": a}))
                dpg.add_checkbox(tag="custom_model", label="Custom Model", default_value=False, callback=lambda s, a: state.update({"custom_model": a}))
                dpg.add_input_text(tag="custom_model_path", label="Model Path", default_value="", callback=lambda s, a: state.update({"custom_model_path": a}))

            with dpg.collapsing_header(label="Interpolate", default_open=False):
                dpg.add_checkbox(tag="interpolate", label="Enable Interpolation", default_value=False, callback=lambda s, a: state.update({"interpolate": a}))
                dpg.add_combo(tag="interpolate_method", label="Method", items=["rife4.6","rife4.22","rife4.25","rife4.25-lite","rife4.25-heavy","gmfss"], default_value="rife4.6", callback=lambda s, a: state.update({"interpolate_method": a}))
                dpg.add_drag_float(tag="interpolate_factor", label="Factor", default_value=2.0, min_value=1.0, max_value=4.0, speed=0.1, callback=lambda s, a: state.update({"interpolate_factor": a}))
                dpg.add_checkbox(tag="ensemble", label="Ensemble", default_value=False, callback=lambda s, a: state.update({"ensemble": a}))
                dpg.add_checkbox(tag="dynamic_scale", label="Dynamic Scale", default_value=False, callback=lambda s, a: state.update({"dynamic_scale": a}))
                dpg.add_checkbox(tag="slowmo", label="Slow Motion", default_value=False, callback=lambda s, a: state.update({"slowmo": a}))
                dpg.add_checkbox(tag="static_step", label="Static Step", default_value=False, callback=lambda s, a: state.update({"static_step": a}))
                dpg.add_checkbox(tag="interpolate_first", label="Interpolate First", default_value=True, callback=lambda s, a: state.update({"interpolate_first": a}))

            with dpg.collapsing_header(label="Restore", default_open=False):
                dpg.add_checkbox(tag="restore", label="Enable Restore", default_value=False, callback=lambda s, a: state.update({"restore": a}))
                dpg.add_combo(tag="restore_method", label="Method", items=["scunet","nafnet","dpir","real-plksr","anime1080fixer","fastlinedarken","autocas","gater3","deh264_real","deh264_span","hurrdeblur"], default_value="anime1080fixer", callback=lambda s, a: state.update({"restore_method": a}))
                dpg.add_checkbox(tag="stabilize", label="Stabilize", default_value=False, callback=lambda s, a: state.update({"stabilize": a}))

            with dpg.collapsing_header(label="Deduplication", default_open=False):
                dpg.add_checkbox(tag="dedup", label="Enable Deduplication", default_value=False, callback=lambda s, a: state.update({"dedup": a}))
                dpg.add_combo(tag="dedup_method", label="Method", items=["ssim","ssim-cuda","mse","mse-cuda","flownets","vmaf","vmaf-cuda"], default_value="ssim", callback=lambda s, a: state.update({"dedup_method": a}))
                dpg.add_drag_int(tag="dedup_sens", label="Sensitivity", default_value=35, min_value=0, max_value=100, callback=lambda s, a: state.update({"dedup_sens": a}))

            with dpg.collapsing_header(label="Segmentation", default_open=False):
                dpg.add_checkbox(tag="segment", label="Enable Segmentation", default_value=False, callback=lambda s, a: state.update({"segment": a}))
                dpg.add_combo(tag="segment_method", label="Method", items=["anime","anime-tensorrt"], default_value="anime", callback=lambda s, a: state.update({"segment_method": a}))

            with dpg.collapsing_header(label="Depth", default_open=False):
                dpg.add_checkbox(tag="depth", label="Enable Depth", default_value=False, callback=lambda s, a: state.update({"depth": a}))
                dpg.add_combo(tag="depth_method", label="Method", items=["small_v2","base_v2","large_v2","giant_v2","distill_small_v2","distill_base_v2","distill_large_v2","og_small_v2","og_base_v2","og_large_v2","og_large_v3"], default_value="small_v2", callback=lambda s, a: state.update({"depth_method": a}))
                dpg.add_combo(tag="depth_quality", label="Quality", items=["low","medium","high"], default_value="low", callback=lambda s, a: state.update({"depth_quality": a}))
                dpg.add_checkbox(tag="depth_norm", label="Depth Norm", default_value=False, callback=lambda s, a: state.update({"depth_norm": a}))

            with dpg.collapsing_header(label="Object Detection", default_open=False):
                dpg.add_checkbox(tag="obj_detect", label="Enable Object Detection", default_value=False, callback=lambda s, a: state.update({"obj_detect": a}))
                dpg.add_combo(tag="obj_detect_method", label="Method", items=["yolov9_small-directml","yolov9_medium-directml","yolov9_large-directml"], default_value="yolov9_small-directml", callback=lambda s, a: state.update({"obj_detect_method": a}))

            with dpg.collapsing_header(label="Auto Clip Detection", default_open=False):
                dpg.add_checkbox(tag="autoclip", label="Enable Auto Clip", default_value=False, callback=lambda s, a: state.update({"autoclip": a}))
                dpg.add_drag_float(tag="autoclip_sens", label="Sensitivity", default_value=50.0, min_value=0.0, max_value=100.0, speed=1.0, callback=lambda s, a: state.update({"autoclip_sens": a}))

            with dpg.collapsing_header(label="Export & Encoding", default_open=True):
                dpg.add_checkbox(tag="resize", label="Resize", default_value=False, callback=lambda s, a: state.update({"resize": a}))
                dpg.add_drag_float(tag="resize_factor", label="Resize Factor", default_value=2.0, min_value=0.1, max_value=10.0, speed=0.1, callback=lambda s, a: state.update({"resize_factor": a}))
                dpg.add_input_text(tag="output_scale", label="Output Scale (e.g. 3840x2160)", default_value="", callback=lambda s, a: state.update({"output_scale": a}))
                dpg.add_combo(tag="encode_method", label="Encode Method", items=["x264","x264_animation","x264_animation_10bit","x264_10bit","x265","x265_10bit","av1","nvenc_h264","nvenc_h265","nvenc_h265_10bit","nvenc_av1","qsv_h264","qsv_h265","qsv_h265_10bit","qsv_vp9","h264_amf","hevc_amf","hevc_amf_10bit","slow_x264","slow_nvenc_h264","slow_x265","slow_nvenc_h265","slow_av1","slow_nvenc_av1","prores","prores_segment","gif","png","vp9","lossless","lossless_nvenc"], default_value="x264", callback=lambda s, a: state.update({"encode_method": a}))
                dpg.add_input_text(tag="custom_encoder", label="Custom Encoder", default_value="", callback=lambda s, a: state.update({"custom_encoder": a}))

            with dpg.collapsing_header(label="Advanced", default_open=False):
                dpg.add_checkbox(tag="half", label="Half precision", default_value=True, callback=lambda s, a: state.update({"half": a}))
                dpg.add_checkbox(tag="static", label="Static mode", default_value=False, callback=lambda s, a: state.update({"static": a}))
                dpg.add_combo(tag="compile_mode", label="Compile mode", items=["default","max","max-graphs"], default_value="default", callback=lambda s, a: state.update({"compile_mode": a}))
                dpg.add_combo(tag="download_req", label="Download reqs", items=["none","windows-cuda","windows-lite","linux-cuda","linux-lite"], default_value="none", callback=lambda s, a: state.update({"download_req": a}))
                dpg.add_checkbox(tag="cleanup", label="Cleanup", default_value=False, callback=lambda s, a: state.update({"cleanup": a}))
                dpg.add_combo(tag="bit_depth", label="Bit depth", items=["8bit","16bit"], default_value="8bit", callback=lambda s, a: state.update({"bit_depth": a}))
                dpg.add_checkbox(tag="benchmark", label="Benchmark", default_value=False, callback=lambda s, a: state.update({"benchmark": a}))
                dpg.add_checkbox(tag="preview", label="Preview", default_value=False, callback=lambda s, a: state.update({"preview": a}))
                dpg.add_checkbox(tag="ae_enable", label="Enable AE", default_value=False, callback=lambda s, a: state.update({"ae_enable": a}))
                dpg.add_input_text(tag="ae_host", label="AE Host", default_value="127.0.0.1:PORT", callback=lambda s, a: state.update({"ae_host": a}))

        with dpg.group(horizontal=True):
            dpg.add_button(label="Run", width=80, callback=lambda: run_process())
            dpg.add_text(tag="status_text", default_value="Ready", color=[180, 180, 180])

        dpg.add_input_text(tag="log_text", multiline=True, readonly=True, default_value="", height=60)

    dpg.set_primary_window("main_win", True)
    dpg.show_viewport()

    while dpg.is_dearpygui_running():
        poll_metadata()
        dpg.render_dearpygui_frame()

    dpg.destroy_context()


# ==============================================================================
# BRIDGE CLI ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    if len(_sys.argv) > 1:
        cmd = _sys.argv[1]
        try:
            if cmd == "probe":
                if _use_subprocess():
                    result = _call_py311("probe")
                    print(_json.dumps(result))
                else:
                    resolve_obj, err = get_resolve()
                    if err:
                        print(_json.dumps({"success": False, "error": err}))
                    else:
                        print(_json.dumps({"success": True}))
            elif cmd == "get_current_clip_metadata":
                result = get_current_clip_metadata()
                result.pop("clip_obj", None)
                print(_json.dumps(result))
            elif cmd == "get_project_path":
                path = get_project_path()
                print(_json.dumps(path))
            elif cmd == "import_clip_to_timeline":
                args = _json.loads(_sys.argv[2])
                err = import_and_align_clip(args["file_path"], args["clip_details"])
                print(_json.dumps({"error": err}))
            else:
                print(_json.dumps({"error": f"Unknown command: {cmd}"}))
        except Exception as e:
            print(_json.dumps({"error": str(e)}))
    else:
        main()
