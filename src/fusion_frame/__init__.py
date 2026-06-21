import sys

from PySide6.QtWidgets import QApplication

from fusion_frame.window import FusionFrameWindow


def run(resolve=None):
    app = QApplication.instance() or QApplication(sys.argv)
    window = FusionFrameWindow(resolve=resolve)
    window.show()
    app.exec()
