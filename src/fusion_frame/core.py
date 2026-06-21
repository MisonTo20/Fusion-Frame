"""
Resolve API logic for Fusion Frame.

Free-version note
------------------
On DaVinci Resolve Free, `DaVinciResolveScript.scriptapp("Resolve")` always
returns None when called from an external/standalone Python process. There
is no workaround for that.

The only thing that works on Free is letting Resolve itself launch a script
from Scripts -> Comp (or Scripts -> Utility), which injects a live `app`
(Fusion) object into that script. From `app.GetResolve()` you get a working
`Resolve` object with full access to the Project Manager, Media Pool, and
Timeline API -- the same object your code used to try to obtain via
scriptapp().

Every function below therefore takes `resolve` as an explicit argument
instead of fetching it internally. The bridge script obtains it once
(via `app.GetResolve()`) and passes it down. Nothing in this module ever
calls scriptapp() or imports DaVinciResolveScript.
"""


def get_current_clip_metadata(resolve):
    """
    Returns metadata about the clip under the playhead on the current
    timeline, or {"success": False, "error": ...} if anything is missing.
    """
    try:
        if not resolve:
            return {"success": False, "error": "No connection to Resolve. Run this from Scripts > Comp."}
        pm = resolve.GetProjectManager()
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
            "clip_name": clip_name,
            "source_path": source_path,
            "start_frame": int(start or 0),
            "duration": int(duration or 0),
            "left_offset": int(left_offset or 0),
            "timeline_framerate": framerate,
        }
    except Exception as e:
        return {"success": False, "error": f"Resolve API error: {e}"}


def get_project_path(resolve):
    try:
        if not resolve:
            return None
        pm = resolve.GetProjectManager()
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


def import_and_align_clip(resolve, file_path, clip_details, **kwargs):
    """
    Imports file_path into the Media Pool, appends it to the timeline,
    then repositions/resizes it to sit exactly where the original clip
    (described by clip_details) was, on a track above (or below) it.

    Returns None on success, or an error string.
    """
    if not resolve:
        return "No connection to Resolve. Run this from Scripts > Comp."
    pm = resolve.GetProjectManager()
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

    current_track = _find_item_track(
        timeline,
        clip_details.get("clip_name", ""),
        clip_details.get("start_frame", 0),
        clip_details.get("duration", 0),
    )
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


def verify_resolve(resolve):
    """
    Standard guard used before any operation that touches Resolve.
    Returns (project, error_str_or_None).
    """
    if resolve is None:
        return None, "Open this plugin from Scripts > Comp in Resolve."
    try:
        pm = resolve.GetProjectManager()
        if not pm:
            return None, "Could not access Project Manager."
        project = pm.GetCurrentProject()
        if not project:
            return None, "No project open."
        return project, None
    except Exception as e:
        return None, f"Resolve API error: {e}"
