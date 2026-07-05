# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Port graphics item: a typed connection point on a node."""

from PySide6 import QtCore, QtGui, QtWidgets

from .. import style

INPUT = "input"
OUTPUT = "output"


class PortItem(QtWidgets.QGraphicsItem):
    """Circular port; child of a NodeItem."""

    def __init__(self, node_item, port_name, type_name, direction,
                 parent=None):
        super().__init__(parent or node_item)
        self.node_item = node_item
        self.port_name = port_name
        self.type_name = type_name
        self.direction = direction
        self._hover = False
        self._highlight = None   # None / True (compatible) / False
        self._snap_active = False
        self.setAcceptHoverEvents(True)
        self.setToolTip("%s : %s" % (port_name, type_name))

    # -------------------------------------------------------------- geometry

    def boundingRect(self):
        r = style.PORT_RADIUS + 6
        return QtCore.QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self):
        path = QtGui.QPainterPath()
        r = style.PORT_RADIUS + 4
        path.addEllipse(QtCore.QPointF(0, 0), r, r)
        return path

    def scene_pos(self):
        return self.mapToScene(QtCore.QPointF(0, 0))

    # -------------------------------------------------------------- painting

    def paint(self, painter, option, widget=None):
        radius = style.PORT_RADIUS
        color = QtGui.QColor(style.type_color(self.type_name))
        if self._highlight is False:
            color = color.darker(280)
        elif self._snap_active:
            color = color.lighter(170)
            radius += 3.0
        elif self._hover or self._highlight:
            color = color.lighter(140)
            radius += 1.5
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if self._snap_active:
            glow = QtGui.QPen(style.SNAP_RING, 2.0)
            painter.setPen(glow)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(QtCore.QPointF(0, 0), radius + 2.5, radius + 2.5)
        painter.setBrush(color)
        painter.setPen(QtGui.QPen(style.PORT_BORDER, 1))
        painter.drawEllipse(QtCore.QPointF(0, 0), radius, radius)

    # ------------------------------------------------------------ interaction

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def set_drag_highlight(self, state):
        """None resets; True marks compatible; False dims incompatible."""
        if self._highlight != state:
            self._highlight = state
            self.update()

    def set_snap_active(self, active):
        """True while this port is the magnetic snap target during a drag."""
        if self._snap_active != active:
            self._snap_active = active
            self.update()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            scene = self.scene()
            if scene is not None and hasattr(scene, "begin_connection"):
                if scene.begin_connection(self):
                    view = scene.host_view() if hasattr(scene, "host_view") \
                        else None
                    if view is not None:
                        view._connecting = True
                    event.accept()
                    return
        super().mousePressEvent(event)

    @property
    def node_name(self):
        return self.node_item.node_name
