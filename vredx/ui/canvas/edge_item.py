# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Edge graphics item: a cubic bezier between two ports."""

from PySide6 import QtCore, QtGui, QtWidgets

from .. import style


def bezier_path(p1: QtCore.QPointF, p2: QtCore.QPointF) -> QtGui.QPainterPath:
    """Horizontal-tangent cubic between two points."""
    path = QtGui.QPainterPath(p1)
    dx = max(abs(p2.x() - p1.x()) * 0.5, 40.0)
    c1 = QtCore.QPointF(p1.x() + dx, p1.y())
    c2 = QtCore.QPointF(p2.x() - dx, p2.y())
    path.cubicTo(c1, c2, p2)
    return path


class EdgeItem(QtWidgets.QGraphicsPathItem):
    """View of one core Edge; endpoints resolved from port items."""

    def __init__(self, edge, src_port, dst_port):
        super().__init__()
        self.edge = edge              # core graph.Edge
        self.src_port = src_port
        self.dst_port = dst_port
        self.setZValue(-1)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        pen = QtGui.QPen(style.EDGE_COLOR, style.EDGE_WIDTH)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        self.setPen(pen)
        self.refresh()

    def refresh(self):
        self.setPath(bezier_path(self.src_port.scene_pos(),
                                 self.dst_port.scene_pos()))

    def paint(self, painter, option, widget=None):
        pen = QtGui.QPen(self.pen())
        pen.setColor(style.EDGE_SELECTED if self.isSelected()
                     else style.EDGE_COLOR)
        self.setPen(pen)
        # Suppress the default selection rectangle.
        option.state &= ~QtWidgets.QStyle.State_Selected
        super().paint(painter, option, widget)

    def shape(self):
        # Fatten the clickable region around the curve.
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())


class DragEdgeItem(QtWidgets.QGraphicsPathItem):
    """Temporary edge shown while the user drags out a connection."""

    def __init__(self, start_pos: QtCore.QPointF):
        super().__init__()
        self.setZValue(10)
        pen = QtGui.QPen(style.EDGE_DRAG, style.EDGE_WIDTH,
                         QtCore.Qt.DashLine)
        self.setPen(pen)
        self._start = start_pos
        self.update_end(start_pos)

    def update_end(self, pos: QtCore.QPointF, reverse=False):
        if reverse:
            self.setPath(bezier_path(pos, self._start))
        else:
            self.setPath(bezier_path(self._start, pos))
