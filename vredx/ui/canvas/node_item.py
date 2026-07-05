# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Node graphics item: rounded box with typed ports.

Nodes with many inputs (standard_surface has 42) start collapsed:
connected inputs, overridden inputs and the first few basic inputs are
shown; a small +/- toggle in the header expands the full list.
"""

from PySide6 import QtCore, QtGui, QtWidgets

from .. import style
from .port_item import INPUT, OUTPUT, PortItem

_COLLAPSED_BASIC_LIMIT = 8


class NodeItem(QtWidgets.QGraphicsItem):

    def __init__(self, node, graph):
        super().__init__()
        self.node = node          # core graph.Node
        self.graph = graph
        self.expanded = False
        self.input_ports = {}     # name -> PortItem
        self.output_ports = {}    # name -> PortItem
        self._rows = []           # [(input name, y)] for label painting
        self._height = style.NODE_HEADER_HEIGHT

        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsMovable |
            QtWidgets.QGraphicsItem.ItemIsSelectable |
            QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(*node.position)
        self.rebuild_ports()

    # ------------------------------------------------------------ model info

    @property
    def node_name(self):
        return self.node.name

    def visible_inputs(self):
        if self.expanded:
            return [i.name for i in self.node.nodedef.inputs]
        connected = {e.dst_input for e in self.graph.edges
                     if e.dst_node == self.node.name}
        names = []
        basic_used = 0
        for idef in self.node.nodedef.inputs:
            if idef.name in connected or idef.name in self.node.values:
                names.append(idef.name)
            elif not idef.advanced and basic_used < _COLLAPSED_BASIC_LIMIT:
                names.append(idef.name)
                basic_used += 1
        return names

    # ------------------------------------------------------------- rebuild

    def rebuild_ports(self):
        self.prepareGeometryChange()
        for port in list(self.input_ports.values()) + \
                list(self.output_ports.values()):
            if port.scene() is not None:
                port.scene().removeItem(port)
            port.setParentItem(None)
        self.input_ports.clear()
        self.output_ports.clear()
        self._rows = []

        y = style.NODE_HEADER_HEIGHT + style.NODE_ROW_HEIGHT / 2.0

        for out in self.node.nodedef.outputs:
            port = PortItem(self, out.name, out.type, OUTPUT)
            port.setPos(style.NODE_WIDTH, y)
            self.output_ports[out.name] = port
            self._rows.append((out.name, y, OUTPUT))
            y += style.NODE_ROW_HEIGHT

        for name in self.visible_inputs():
            idef = self.node.nodedef.find_input(name)
            port = PortItem(self, name, idef.type, INPUT)
            port.setPos(0, y)
            self.input_ports[name] = port
            self._rows.append((name, y, INPUT))
            y += style.NODE_ROW_HEIGHT

        hidden = len(self.node.nodedef.inputs) - len(self.input_ports)
        self._hidden_count = max(0, hidden)
        if self._hidden_count and not self.expanded:
            y += style.NODE_ROW_HEIGHT * 0.8
        self._height = y + style.NODE_ROW_HEIGHT / 2.0

    def toggle_expanded(self):
        self.expanded = not self.expanded
        self.rebuild_ports()
        scene = self.scene()
        if scene is not None and hasattr(scene, "refresh_edges"):
            scene.refresh_edges()
        self.update()

    # ------------------------------------------------------------- geometry

    def boundingRect(self):
        return QtCore.QRectF(-2, -2, style.NODE_WIDTH + 4, self._height + 4)

    def _toggle_rect(self):
        return QtCore.QRectF(style.NODE_WIDTH - 20, 5, 14, 14)

    # ------------------------------------------------------------- painting

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(0, 0, style.NODE_WIDTH, self._height)

        body = style.OPAQUE_NODE_BODY if self.node.opaque else (
            style.NODE_BODY_SELECTED if self.isSelected()
            else style.NODE_BODY)
        border = (style.NODE_BORDER_SELECTED if self.isSelected()
                  else style.NODE_BORDER)
        painter.setBrush(body)
        painter.setPen(QtGui.QPen(border, 1.4))
        painter.drawRoundedRect(rect, style.NODE_RADIUS, style.NODE_RADIUS)

        # Header band tinted by nodegroup.
        header = QtGui.QPainterPath()
        header.addRoundedRect(
            QtCore.QRectF(0, 0, style.NODE_WIDTH, style.NODE_HEADER_HEIGHT),
            style.NODE_RADIUS, style.NODE_RADIUS)
        header.addRect(QtCore.QRectF(
            0, style.NODE_HEADER_HEIGHT / 2.0,
            style.NODE_WIDTH, style.NODE_HEADER_HEIGHT / 2.0))
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(style.group_color(self.node.nodedef.nodegroup))
        painter.drawPath(header.simplified())

        # Title: node name (bold) + category.
        painter.setPen(style.NODE_TEXT)
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(8.5)
        painter.setFont(font)
        title_rect = QtCore.QRectF(8, 0, style.NODE_WIDTH - 30,
                                   style.NODE_HEADER_HEIGHT)
        title = self.node.name
        if self.node.name != self.node.category:
            title = "%s  (%s)" % (self.node.name, self.node.category)
        painter.drawText(title_rect,
                         QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                         painter.fontMetrics().elidedText(
                             title, QtCore.Qt.ElideRight,
                             int(title_rect.width())))

        # Expand toggle.
        if self.node.nodedef.inputs:
            painter.setPen(QtGui.QPen(style.NODE_TEXT, 1.2))
            trect = self._toggle_rect()
            cy = trect.center().y()
            painter.drawLine(QtCore.QPointF(trect.left() + 3, cy),
                             QtCore.QPointF(trect.right() - 3, cy))
            if not self.expanded:
                cx = trect.center().x()
                painter.drawLine(QtCore.QPointF(cx, trect.top() + 3),
                                 QtCore.QPointF(cx, trect.bottom() - 3))

        # Port labels.
        font.setBold(False)
        font.setPointSizeF(7.5)
        painter.setFont(font)
        for name, y, direction in self._rows:
            row = QtCore.QRectF(12, y - style.NODE_ROW_HEIGHT / 2.0,
                                style.NODE_WIDTH - 24, style.NODE_ROW_HEIGHT)
            painter.setPen(style.NODE_SUBTEXT)
            if direction == OUTPUT:
                painter.drawText(row, QtCore.Qt.AlignVCenter |
                                 QtCore.Qt.AlignRight, name)
            else:
                overridden = name in self.node.values
                painter.setPen(style.NODE_TEXT if overridden
                               else style.NODE_SUBTEXT)
                painter.drawText(
                    row, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                    painter.fontMetrics().elidedText(
                        name, QtCore.Qt.ElideRight, int(row.width())))

        # Hidden-input hint.
        if self._hidden_count and not self.expanded:
            painter.setPen(style.NODE_SUBTEXT)
            hint_rect = QtCore.QRectF(
                12, self._height - style.NODE_ROW_HEIGHT * 1.2,
                style.NODE_WIDTH - 24, style.NODE_ROW_HEIGHT)
            painter.drawText(hint_rect,
                             QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                             "+ %d more..." % self._hidden_count)

    # ---------------------------------------------------------- interaction

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and \
                self._toggle_rect().contains(event.pos()):
            self.toggle_expanded()
            event.accept()
            return
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()
            if scene is not None and hasattr(scene, "refresh_edges"):
                scene.refresh_edges()
        return super().itemChange(change, value)
