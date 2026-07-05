# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Modal progress UI for long-running VRED MaterialX apply operations."""

from PySide6 import QtCore, QtWidgets


class ApplyProgressDialog(QtWidgets.QProgressDialog):
    """Indeterminate progress while VRED compiles a MaterialX document.

    VRED's Python API must run on the main thread, so this dialog keeps the
    UI responsive via ``processEvents`` rather than using a worker thread.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VredXRoot")
        self.setWindowTitle("VredX")
        self.setLabelText("Applying MaterialX to VRED…")
        self.setRange(0, 0)
        self.setMinimumDuration(0)
        self.setAutoClose(True)
        self.setAutoReset(True)
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.setCancelButton(None)

    def pulse(self, message: str):
        self.setLabelText(message)
        QtWidgets.QApplication.processEvents()
