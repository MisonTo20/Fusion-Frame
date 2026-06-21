# bridge/FusionFrame.py
#
# Copy this file to Resolve's Scripts/Comp/ folder:
#   Windows: %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Comp\
#   Mac:     ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Comp/
#   Linux:   ~/.local/share/DaVinciResolve/Fusion/Scripts/Comp/
#
# Resolve runs this script itself when you click Scripts > Comp > FusionFrame
# (you need a clip open on the Fusion page for the menu item to appear).
# Because Resolve launches it, `app` already exists in this script's globals
# -- Resolve injects it. That is what makes Resolve-API access work on the
# Free version: no DaVinciResolveScript.scriptapp() call is used anywhere.
#
# All this file does is point Python at the plugin source and hand off the
# live Resolve object.

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# EDIT THIS: point to the "src" folder of the Fusion Frame plugin.
# ---------------------------------------------------------------------------
PLUGIN_SRC = r"C:\Path\To\fusion_frame\src"   # Windows -- adjust
# PLUGIN_SRC = "/Users/yourname/fusion_frame/src"   # Mac
# PLUGIN_SRC = "/home/yourname/fusion_frame/src"    # Linux

sys.path.insert(0, str(Path(PLUGIN_SRC)))

# Optional, useful while developing: forces Python to re-import the plugin
# package every time you trigger it from the Scripts menu, so code edits are
# picked up without restarting Resolve. Remove this block once the plugin
# is finished to shave a little overhead off each launch.
import importlib
for _key in [k for k in list(sys.modules) if k.startswith("fusion_frame")]:
    del sys.modules[_key]

from fusion_frame import run

# `app` is injected by Resolve -- it is the active Fusion instance.
# app.GetResolve() returns the top-level Resolve object: Project Manager,
# Media Pool, Timeline API, everything Fusion Frame needs.
resolve = app.GetResolve()
run(resolve=resolve)
