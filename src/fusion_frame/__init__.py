"""
Fusion Frame plugin entry point.

Called by the bridge script (Scripts/Comp/FusionFrame.py) which Resolve
launches when the user clicks Scripts > Comp > FusionFrame.

`run(resolve=...)` receives a live Resolve object that the bridge obtained
via `app.GetResolve()` -- `app` being the Fusion instance Resolve injects
automatically. This is the only mechanism for Resolve-API access that
works on the Free version; scriptapp() based connections do not.
"""
import sys

from PySide6.QtWidgets import QApplication

from fusion_frame.window import FusionFrameWindow


def run(resolve=None):
    app = QApplication.instance() or QApplication(sys.argv)
    window = FusionFrameWindow(resolve=resolve)
    window.show()
    app.exec()
