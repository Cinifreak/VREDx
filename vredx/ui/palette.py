# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Node palette: every supported MaterialX node, draggable onto the canvas.

The tree is generated from the parsed VRED libraries, grouped by
MaterialX nodegroup, with a search filter.  Dragging an entry starts a
QDrag carrying the nodedef name; the canvas scene creates the node on
drop.  Double-clicking adds the node at the canvas center.
"""

from PySide6 import QtCore, QtGui, QtWidgets

from .canvas.scene import NODEDEF_MIME

# Friendlier display labels for MaterialX nodegroups.
GROUP_LABELS = {
    "material": "Materials",
    "pbr": "PBR Shading",
    "shader": "Shaders",
    "texture2d": "Textures 2D",
    "texture3d": "Textures 3D",
    "procedural": "Procedural",
    "procedural2d": "Procedural 2D",
    "procedural3d": "Procedural 3D",
    "geometric": "Geometry",
    "math": "Math",
    "adjustment": "Adjustment",
    "compositing": "Compositing",
    "conditional": "Conditional",
    "channel": "Channels",
    "colortransform": "Color Transform",
    "convolution2d": "Convolution",
    "npr": "NPR",
    "organization": "Organization",
    "application": "Application",
    "other": "Other",
}

# Order in which groups appear (unlisted groups follow alphabetically).
GROUP_ORDER = [
    "material", "pbr", "shader", "texture2d", "procedural2d",
    "procedural3d", "procedural", "geometric", "math", "adjustment",
    "compositing", "conditional", "channel", "colortransform",
    "convolution2d", "npr", "texture3d",
]


class PaletteTree(QtWidgets.QTreeWidget):
    """Tree widget that starts nodedef drags."""

    add_requested = QtCore.Signal(str)   # nodedef name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAlternatingRowColors(True)
        self.itemActivated.connect(self._on_activated)

    def startDrag(self, actions):
        item = self.currentItem()
        if item is None:
            return
        nodedef_name = item.data(0, QtCore.Qt.UserRole)
        if not nodedef_name:
            return
        mime = QtCore.QMimeData()
        mime.setData(NODEDEF_MIME, nodedef_name.encode("utf-8"))
        mime.setText(item.text(0))
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        drag.exec(QtCore.Qt.CopyAction)

    def _on_activated(self, item, _column):
        nodedef_name = item.data(0, QtCore.Qt.UserRole)
        if nodedef_name:
            self.add_requested.emit(nodedef_name)


class PalettePanel(QtWidgets.QWidget):
    """Search box + grouped node tree."""

    add_requested = QtCore.Signal(str)   # nodedef name

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.search = QtWidgets.QLineEdit(self)
        self.search.setPlaceholderText("Search nodes...")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self.tree = PaletteTree(self)
        layout.addWidget(self.tree)

        self.count_label = QtWidgets.QLabel(self)
        layout.addWidget(self.count_label)

        self.search.textChanged.connect(self.populate)
        self.tree.add_requested.connect(self.add_requested)
        self.populate()

    def populate(self, filter_text: str = ""):
        filter_text = (filter_text or "").lower().strip()
        self.tree.clear()
        groups = self.library.groups()

        ordered = [g for g in GROUP_ORDER if g in groups]
        ordered += sorted(g for g in groups if g not in GROUP_ORDER)

        shown = 0
        for group in ordered:
            nodes = [n for n in groups[group]
                     if self._node_visible(n, filter_text)]
            if not nodes:
                continue
            group_item = QtWidgets.QTreeWidgetItem(
                [GROUP_LABELS.get(group, group.title())])
            group_item.setFlags(QtCore.Qt.ItemIsEnabled)
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            self.tree.addTopLevelItem(group_item)

            for node_name in nodes:
                all_variants = self.library.variants(node_name)
                if not all_variants:
                    continue
                variants = self._filtered_variants(
                    node_name, all_variants, filter_text)
                if not variants:
                    continue
                shown += 1
                if len(all_variants) == 1:
                    self._add_leaf(group_item, node_name, variants[0])
                elif len(variants) == 1 and filter_text:
                    label = "%s  (%s)" % (node_name, variants[0].type_signature())
                    self._add_leaf(group_item, label, variants[0])
                else:
                    parent = QtWidgets.QTreeWidgetItem([node_name])
                    # Default drag: first variant.
                    parent.setData(0, QtCore.Qt.UserRole, variants[0].name)
                    parent.setFlags(parent.flags() |
                                    QtCore.Qt.ItemIsDragEnabled)
                    group_item.addChild(parent)
                    for nd in variants:
                        self._add_leaf(parent, nd.type_signature(), nd)

            group_item.setExpanded(bool(filter_text))

        total = len(self.library.node_names())
        self.count_label.setText("%d / %d node types" % (shown, total))
        if filter_text:
            self.tree.expandAll()

    def _node_visible(self, node_name, filter_text):
        if not filter_text:
            return True
        if filter_text in node_name.lower():
            return True
        return any(nd.matches_filter(filter_text, node_name)
                   for nd in self.library.variants(node_name))

    def _filtered_variants(self, node_name, all_variants, filter_text):
        if not filter_text:
            return all_variants
        if filter_text in node_name.lower():
            return all_variants
        return [nd for nd in all_variants
                if nd.matches_filter(filter_text, node_name)]

    def _add_leaf(self, parent_item, label, nodedef):
        item = QtWidgets.QTreeWidgetItem([label])
        item.setData(0, QtCore.Qt.UserRole, nodedef.name)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsDragEnabled)
        item.setToolTip(0, nodedef.palette_tooltip())
        parent_item.addChild(item)
