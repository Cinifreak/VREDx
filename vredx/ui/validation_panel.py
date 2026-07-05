# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Validation panel: live list of errors/warnings from the validator."""

from PySide6 import QtCore, QtGui, QtWidgets

from ..core import validator

_SEVERITY_COLORS = {
    validator.ERROR: QtGui.QColor(235, 100, 100),
    validator.WARNING: QtGui.QColor(230, 190, 90),
    validator.INFO: QtGui.QColor(130, 170, 220),
}

_SEVERITY_LABEL = {
    validator.ERROR: "Error",
    validator.WARNING: "Warning",
    validator.INFO: "Info",
}


class ValidationPanel(QtWidgets.QWidget):
    """Re-validates on demand; clicking an issue selects its node."""

    issue_selected = QtCore.Signal(str)   # node name

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.summary = QtWidgets.QLabel("Not validated yet.")
        layout.addWidget(self.summary)

        self.list = QtWidgets.QListWidget(self)
        self.list.setAlternatingRowColors(True)
        self.list.setWordWrap(True)
        layout.addWidget(self.list)
        self.list.itemClicked.connect(self._on_clicked)

    def show_result(self, result: validator.ValidationResult):
        self.list.clear()
        for issue in result.issues:
            text = "%s: %s" % (_SEVERITY_LABEL[issue.severity],
                               issue.message)
            if issue.node:
                text = "[%s] %s" % (issue.node, text)
            item = QtWidgets.QListWidgetItem(text)
            item.setForeground(_SEVERITY_COLORS[issue.severity])
            item.setData(QtCore.Qt.UserRole, issue.node or "")
            self.list.addItem(item)

        n_err = len(result.errors)
        n_warn = len(result.warnings)
        if not result.issues:
            self.summary.setText("Document is valid.")
            self.summary.setStyleSheet("color: #7aa87a;")
        elif n_err:
            self.summary.setText("%d error(s), %d warning(s) - fix errors "
                                 "before sending to VRED." % (n_err, n_warn))
            self.summary.setStyleSheet("color: #eb6464;")
        else:
            self.summary.setText("%d warning(s); document will load."
                                 % n_warn)
            self.summary.setStyleSheet("color: #e6be5a;")

    def _on_clicked(self, item):
        node = item.data(QtCore.Qt.UserRole)
        if node:
            self.issue_selected.emit(node)
