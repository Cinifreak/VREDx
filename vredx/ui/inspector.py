# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Property inspector: typed editors for the selected node's inputs.

Editors are generated from the NodeDef input metadata (type, uimin/uimax,
enum values, uifolder grouping).  Edits go through undoable
SetValueCommands; continuous slider drags merge into one undo step.
"""

import html
from functools import partial

from PySide6 import QtCore, QtGui, QtWidgets

from ..core import commands, mtlx_types
from ..core.graph import can_expose_in_material, expose_check_state
from .color_dialog import pick_color


class FloatSlider(QtWidgets.QWidget):
    """Slider + spinbox pair honoring uimin/uimax (soft range fallback)."""

    value_changed = QtCore.Signal(float)

    def __init__(self, lo, hi, parent=None):
        super().__init__(parent)
        self._lo, self._hi = lo, hi
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider.setRange(0, 1000)
        self.spin = QtWidgets.QDoubleSpinBox(self)
        self.spin.setDecimals(4)
        self.spin.setRange(-1e9, 1e9)
        self.spin.setSingleStep(max((hi - lo) / 100.0, 0.001))
        self.spin.setFixedWidth(78)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self._updating = False

    def set_value(self, value):
        self._updating = True
        self.spin.setValue(float(value))
        self._sync_slider(float(value))
        self._updating = False

    def _sync_slider(self, value):
        span = self._hi - self._lo
        if span > 0:
            t = max(0.0, min(1.0, (value - self._lo) / span))
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(t * 1000)))
            self.slider.blockSignals(False)

    def _from_slider(self, ticks):
        if self._updating:
            return
        value = self._lo + (self._hi - self._lo) * ticks / 1000.0
        self._updating = True
        self.spin.setValue(value)
        self._updating = False
        self.value_changed.emit(value)

    def _from_spin(self, value):
        if self._updating:
            return
        self._sync_slider(value)
        self.value_changed.emit(value)


class ColorButton(QtWidgets.QPushButton):
    """Swatch button opening a VRED-styled color picker (color3/color4)."""

    color_changed = QtCore.Signal(tuple)

    def __init__(self, channels=3, parent=None):
        super().__init__(parent)
        self.channels = channels
        self._value = tuple(0.0 for _ in range(channels))
        self.clicked.connect(self._pick)
        self.setFixedHeight(22)

    def set_value(self, value):
        value = tuple(value) if value else tuple(
            0.0 for _ in range(self.channels))
        self._value = value
        rgb = [int(max(0.0, min(1.0, c)) * 255) for c in value[:3]]
        self.setStyleSheet(
            "background-color: rgb(%d,%d,%d); color: %s;"
            " border: 1px solid #444448; border-radius: 3px;"
            " padding: 2px 6px;"
            % (rgb[0], rgb[1], rgb[2],
               "#111" if sum(rgb) > 382 else "#e0e0e0"))
        self.setText("%.3f, %.3f, %.3f" % value[:3] if len(value) >= 3
                     else str(value))

    def _pick(self):
        initial = QtGui.QColor.fromRgbF(
            *[max(0.0, min(1.0, c)) for c in self._value[:3]])
        parent = self.window()
        picked = pick_color(initial, parent)
        if picked is None:
            return
        value = picked
        if self.channels == 4:
            alpha = self._value[3] if len(self._value) > 3 else 1.0
            value = value + (alpha,)
        self.set_value(value)
        self.color_changed.emit(value)


class VectorEdit(QtWidgets.QWidget):
    """N spinboxes for vectorN / colorN typed as plain numbers."""

    value_changed = QtCore.Signal(tuple)

    def __init__(self, channels, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.spins = []
        for _ in range(channels):
            spin = QtWidgets.QDoubleSpinBox(self)
            spin.setDecimals(4)
            spin.setRange(-1e9, 1e9)
            spin.valueChanged.connect(self._emit)
            layout.addWidget(spin)
            self.spins.append(spin)
        self._updating = False

    def set_value(self, value):
        self._updating = True
        value = value or tuple(0.0 for _ in self.spins)
        for spin, component in zip(self.spins, value):
            spin.setValue(float(component))
        self._updating = False

    def _emit(self, _v):
        if not self._updating:
            self.value_changed.emit(
                tuple(s.value() for s in self.spins))


class FileEdit(QtWidgets.QWidget):
    """Line edit + browse button for filename inputs."""

    value_changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QtWidgets.QLineEdit(self)
        button = QtWidgets.QPushButton("...", self)
        button.setFixedWidth(28)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)
        self.edit.editingFinished.connect(
            lambda: self.value_changed.emit(self.edit.text()))
        button.clicked.connect(self._browse)

    def set_value(self, value):
        self.edit.setText(str(value or ""))

    def _browse(self):
        path, _f = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose texture", self.edit.text(),
            "Images (*.png *.jpg *.jpeg *.exr *.hdr *.tif *.tiff *.bmp);;"
            "All files (*)")
        if path:
            self.edit.setText(path)
            self.value_changed.emit(path)


class InspectorPanel(QtWidgets.QWidget):
    """Material settings and editors for the currently selected node."""

    def __init__(self, stack: commands.CommandStack, parent=None):
        super().__init__(parent)
        self.stack = stack
        self.graph = None
        self.node = None
        self.nodes = []
        self._expose_targets = []
        self._expose_checkbox = None
        self._dissolve_callback = None
        self.active_scope = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        material_box = QtWidgets.QGroupBox("Material", self)
        material_form = QtWidgets.QFormLayout(material_box)
        material_form.setContentsMargins(8, 8, 8, 8)
        material_form.setLabelAlignment(QtCore.Qt.AlignRight)
        self.material_name = QtWidgets.QLineEdit(material_box)
        self.material_name.setPlaceholderText("Material name")
        self.material_name.editingFinished.connect(self._commit_material_name)
        material_form.addRow("Name", self.material_name)
        layout.addWidget(material_box)

        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        layout.addWidget(self.scroll, 1)

        self._placeholder()

    # --------------------------------------------------------------- public

    def set_dissolve_callback(self, callback):
        self._dissolve_callback = callback

    def set_material_name(self, name):
        """Sync the material name field without triggering edits."""
        self.material_name.blockSignals(True)
        self.material_name.setText(name or "")
        self.material_name.blockSignals(False)

    def show_node(self, graph, node, active_scope=None):
        """Show one node, or a placeholder when *node* is None."""
        nodes = [node] if node is not None else []
        self.show_selection(graph, nodes, active_scope=active_scope)

    def show_selection(self, graph, nodes, active_scope=None):
        self.graph = graph
        self.nodes = list(nodes or [])
        self.active_scope = active_scope
        self.node = self.nodes[0] if len(self.nodes) == 1 else None
        self._expose_targets = []
        self._expose_checkbox = None
        if graph is not None:
            self.set_material_name(graph.name)
        if not self.nodes:
            self._placeholder()
            return
        if len(self.nodes) == 1:
            self._build_single_node_panel(self.nodes[0])
        else:
            self._build_multi_node_panel(self.nodes)

    def _build_multi_node_panel(self, nodes):
        container = QtWidgets.QWidget()
        container.setObjectName("VredXRoot")
        outer = QtWidgets.QVBoxLayout(container)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        name_row = QtWidgets.QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_label = QtWidgets.QLabel(
            "<b>%d nodes selected</b>" % len(nodes))
        name_label.setTextFormat(QtCore.Qt.RichText)
        name_row.addWidget(name_label, 1)
        self._add_expose_checkbox(name_row, nodes)
        name_widget = QtWidgets.QWidget()
        name_widget.setLayout(name_row)
        outer.addWidget(name_widget)

        names = QtWidgets.QLabel(
            "<span style='color:#9a9a9f'>%s</span>"
            % html.escape(", ".join(n.name for n in nodes)))
        names.setTextFormat(QtCore.Qt.RichText)
        names.setWordWrap(True)
        outer.addWidget(names)
        outer.addStretch(1)
        self.scroll.setWidget(container)

    def _build_single_node_panel(self, node):
        graph = self.graph
        container = QtWidgets.QWidget()
        container.setObjectName("VredXRoot")
        outer = QtWidgets.QVBoxLayout(container)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        name_row = QtWidgets.QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_label = QtWidgets.QLabel("<b>%s</b>" % html.escape(node.name))
        name_label.setTextFormat(QtCore.Qt.RichText)
        name_row.addWidget(name_label, 1)
        self._add_expose_checkbox(name_row, [node])
        name_widget = QtWidgets.QWidget()
        name_widget.setLayout(name_row)
        outer.addWidget(name_widget)

        subtitle = QtWidgets.QLabel(
            "<span style='color:#9a9a9f'>%s — %s</span>"
            % (html.escape(node.category), html.escape(node.nodedef.library)))
        subtitle.setTextFormat(QtCore.Qt.RichText)
        outer.addWidget(subtitle)

        if self.active_scope and node.compound != self.active_scope:
            scope_hint = QtWidgets.QLabel(
                "This node lives outside the nested graph you are viewing.")
            scope_hint.setWordWrap(True)
            scope_hint.setStyleSheet("color: #c9a227;")
            outer.addWidget(scope_hint)
        elif self._can_author_compound_exports(node):
            self._build_compound_export_section(container, node)
        elif self._can_manage_compound_proxy(node):
            self._build_compound_proxy_section(container, node)

        if node.nodedef.doc:
            doc = QtWidgets.QLabel(node.nodedef.doc)
            doc.setWordWrap(True)
            doc.setStyleSheet("color: #9a9a9f;")
            outer.addWidget(doc)

        connected = {e.dst_input for e in graph.edges
                     if e.dst_node == node.name}

        folders = {}
        for idef in node.nodedef.inputs:
            folders.setdefault(idef.uifolder or "", []).append(idef)

        for folder, inputs in folders.items():
            box = QtWidgets.QGroupBox(folder or "Inputs", container)
            form = QtWidgets.QFormLayout(box)
            form.setLabelAlignment(QtCore.Qt.AlignRight)
            form.setContentsMargins(8, 4, 8, 8)
            for idef in inputs:
                label = idef.uiname or idef.name
                if idef.name in connected:
                    widget = QtWidgets.QLabel("(connected)")
                    widget.setStyleSheet("color: #7aa87a;")
                else:
                    widget = self._editor_for(idef)
                if idef.doc:
                    widget.setToolTip(idef.doc)
                form.addRow(label, widget)
            outer.addWidget(box)

        outer.addStretch(1)
        self.scroll.setWidget(container)

    def _add_expose_checkbox(self, layout, nodes):
        self._expose_targets = [
            n for n in nodes if can_expose_in_material(n, self.graph)]
        state = expose_check_state(nodes, self.graph)
        if state is None:
            return
        expose = QtWidgets.QCheckBox("Expose in material")
        expose.setTristate(len(nodes) > 1)
        expose.setToolTip(
            "Show selected node(s) in VRED's Realistic material editor. "
            "Works for nodes inside nested nodegraphs too.")
        expose.blockSignals(True)
        if state == "checked":
            expose.setCheckState(QtCore.Qt.Checked)
        elif state == "partial":
            expose.setCheckState(QtCore.Qt.PartiallyChecked)
        else:
            expose.setCheckState(QtCore.Qt.Unchecked)
        expose.blockSignals(False)
        expose.stateChanged.connect(self._commit_expose_state)
        self._expose_checkbox = expose
        layout.addWidget(expose, 0, QtCore.Qt.AlignRight)

    def sync_expose_checkbox(self):
        """Refresh the expose toggle after undo/redo without rebuilding."""
        if self._expose_checkbox is None or not self.nodes:
            return
        state = expose_check_state(self.nodes, self.graph)
        if state is None:
            return
        self._expose_checkbox.blockSignals(True)
        if state == "checked":
            self._expose_checkbox.setCheckState(QtCore.Qt.Checked)
        elif state == "partial":
            self._expose_checkbox.setCheckState(QtCore.Qt.PartiallyChecked)
        else:
            self._expose_checkbox.setCheckState(QtCore.Qt.Unchecked)
        self._expose_checkbox.blockSignals(False)

    def _can_author_compound_exports(self, node):
        return (self.active_scope
                and node.compound == self.active_scope
                and not node.is_compound
                and self.active_scope in self.graph.compounds)

    def _can_manage_compound_proxy(self, node):
        return (self.active_scope is None
                and node.is_compound
                and node.name in self.graph.compounds)

    def _build_compound_proxy_section(self, parent, node):
        compound = node.name
        box = QtWidgets.QGroupBox("Graph outputs", parent)
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(6)

        hint = QtWidgets.QLabel(
            "Double-click this group node to open the nested graph, "
            "then right-click an internal node and choose "
            "<b>Add graph output\u2026</b>.")
        hint.setWordWrap(True)
        hint.setTextFormat(QtCore.Qt.RichText)
        hint.setStyleSheet("color: #9a9a9f;")
        layout.addWidget(hint)

        outputs = self.graph.compounds.get(compound, ())
        if outputs:
            for output in outputs:
                row = QtWidgets.QHBoxLayout()
                text = QtWidgets.QLabel(
                    "<span style='color:#96be76'>%s</span>"
                    " <span style='color:#9a9a9f'>(%s · %s → %s)</span>"
                    % (html.escape(output.name),
                       html.escape(output.type),
                       html.escape(output.internal_node),
                       html.escape(output.internal_output)))
                text.setTextFormat(QtCore.Qt.RichText)
                row.addWidget(text, 1)
                remove = QtWidgets.QPushButton("Remove")
                remove.clicked.connect(
                    partial(self._remove_compound_output, output.name))
                row.addWidget(remove)
                wrap = QtWidgets.QWidget()
                wrap.setLayout(row)
                layout.addWidget(wrap)
        else:
            empty = QtWidgets.QLabel("No outputs exported yet.")
            empty.setStyleSheet("color: #9a9a9f;")
            layout.addWidget(empty)

        dissolve = QtWidgets.QPushButton("Dissolve compound graph")
        dissolve.setToolTip(
            "Move all internal nodes back to the root graph and remove "
            "this group node.")
        dissolve.clicked.connect(
            partial(self._request_dissolve_compound, compound))
        layout.addWidget(dissolve)
        parent.layout().addWidget(box)

    def _build_compound_export_section(self, parent, node):
        compound = self.active_scope
        box = QtWidgets.QGroupBox("Graph outputs", parent)
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(6)

        hint = QtWidgets.QLabel(
            "Expose this node's output on the parent group node, or use "
            "right-click \u2192 <b>Add graph output\u2026</b>.")
        hint.setWordWrap(True)
        hint.setTextFormat(QtCore.Qt.RichText)
        hint.setStyleSheet("color: #9a9a9f;")
        layout.addWidget(hint)

        existing = [o for o in self.graph.compounds.get(compound, ())
                    if o.internal_node == node.name]
        if existing:
            for output in existing:
                row = QtWidgets.QHBoxLayout()
                text = QtWidgets.QLabel(
                    "<span style='color:#96be76'>%s</span>"
                    " <span style='color:#9a9a9f'>(%s · %s)</span>"
                    % (html.escape(output.name),
                       html.escape(output.internal_output),
                       html.escape(output.type)))
                text.setTextFormat(QtCore.Qt.RichText)
                row.addWidget(text, 1)
                remove = QtWidgets.QPushButton("Remove")
                remove.clicked.connect(
                    partial(self._remove_compound_output, output.name))
                row.addWidget(remove)
                wrap = QtWidgets.QWidget()
                wrap.setLayout(row)
                layout.addWidget(wrap)
        else:
            hint = QtWidgets.QLabel(
                "This node is not exported from the nested graph yet.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #9a9a9f;")
            layout.addWidget(hint)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        outputs = list(node.nodedef.outputs)
        if len(outputs) > 1:
            port_combo = QtWidgets.QComboBox()
            for odef in outputs:
                port_combo.addItem("%s (%s)" % (odef.name, odef.type), odef.name)
            form.addRow("Port", port_combo)
        else:
            port_combo = None
            default_port = outputs[0].name if outputs else "out"
            form.addRow("Port", QtWidgets.QLabel(default_port))

        default_name = self.graph.unique_compound_output_name(
            compound, "%s_output" % node.name)
        name_edit = QtWidgets.QLineEdit(default_name)
        form.addRow("Output name", name_edit)
        layout.addLayout(form)

        add = QtWidgets.QPushButton("Add graph output")
        add.setToolTip(
            "Expose this node's output on the compound group node at the "
            "parent graph level.")
        add.clicked.connect(
            partial(self._add_compound_output, port_combo, name_edit))
        layout.addWidget(add)
        parent.layout().addWidget(box)

    def _request_dissolve_compound(self, compound_name):
        if self._dissolve_callback is not None:
            self._dissolve_callback(compound_name)

    def _add_compound_output(self, port_combo, name_edit):
        if self.node is None or not self.active_scope:
            return
        name = name_edit.text().strip()
        if not name:
            return
        if port_combo is not None:
            port = port_combo.currentData()
        else:
            port = self.node.nodedef.outputs[0].name
        self.stack.push(commands.AddCompoundOutputCommand(
            self.graph, self.active_scope, name,
            self.node.name, port))
        QtCore.QTimer.singleShot(
            0, lambda: self.show_selection(
                self.graph, [self.node], self.active_scope))

    def _remove_compound_output(self, output_name):
        compound = self.active_scope or (
            self.node.name if self.node and self.node.is_compound else None)
        if not compound:
            return
        node = self.node
        self.stack.push(commands.RemoveCompoundOutputCommand(
            self.graph, compound, output_name))
        if node is not None:
            QtCore.QTimer.singleShot(
                0, lambda: self.show_selection(
                    self.graph, [node],
                    active_scope=self.active_scope))

    # -------------------------------------------------------------- editors

    def _editor_for(self, idef):
        value = self.node.get_value(idef.name)
        type_name = idef.type

        if idef.enum_values:
            combo = QtWidgets.QComboBox()
            combo.addItems(list(idef.enum_values))
            if value in idef.enum_values:
                combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(
                partial(self._commit, idef.name))
            return combo

        if type_name == "float":
            lo = _scalar(idef.uimin, _scalar(idef.uisoftmin, 0.0))
            hi = _scalar(idef.uimax, _scalar(idef.uisoftmax, 1.0))
            if hi <= lo:
                hi = lo + 1.0
            slider = FloatSlider(lo, hi)
            slider.set_value(value if value is not None else 0.0)
            slider.value_changed.connect(
                partial(self._commit_merged, idef.name))
            return slider

        if type_name == "integer":
            spin = QtWidgets.QSpinBox()
            spin.setRange(-10**9, 10**9)
            spin.setValue(int(value) if value is not None else 0)
            spin.valueChanged.connect(partial(self._commit, idef.name))
            return spin

        if type_name == "boolean":
            check = QtWidgets.QCheckBox()
            check.setChecked(bool(value))
            check.toggled.connect(partial(self._commit, idef.name))
            return check

        if type_name in ("color3", "color4"):
            button = ColorButton(mtlx_types.TUPLE_SIZES[type_name])
            button.set_value(value)
            button.color_changed.connect(partial(self._commit, idef.name))
            return button

        if type_name in ("vector2", "vector3", "vector4"):
            vec = VectorEdit(mtlx_types.TUPLE_SIZES[type_name])
            vec.set_value(value)
            vec.value_changed.connect(
                partial(self._commit_merged, idef.name))
            return vec

        if type_name == "filename":
            fedit = FileEdit()
            fedit.set_value(value)
            fedit.value_changed.connect(partial(self._commit, idef.name))
            return fedit

        if type_name in ("string", "geomname"):
            edit = QtWidgets.QLineEdit(str(value or ""))
            edit.editingFinished.connect(
                lambda e=edit, n=idef.name: self._commit(n, e.text()))
            return edit

        label = QtWidgets.QLabel("(%s)" % type_name)
        label.setStyleSheet("color: #808085;")
        return label

    # -------------------------------------------------------------- commits

    def _commit_material_name(self):
        name = self.material_name.text().strip()
        if self.graph is not None and name:
            self.graph.name = name

    def _commit(self, input_name, value):
        if self.node is None:
            return
        self.stack.push(commands.SetValueCommand(
            self.graph, self.node.name, input_name, value))

    def _commit_expose_state(self, state):
        if state == QtCore.Qt.PartiallyChecked or not self._expose_targets:
            return
        exposed = state == QtCore.Qt.Checked
        names = [n.name for n in self._expose_targets]
        # Defer the undo step until Qt finishes the click handler.  Pushing
        # during QAbstractButton::click rebuilds the inspector (via scene
        # sync + selectionChanged) and has crashed VRED in QAccessible code.
        QtCore.QTimer.singleShot(
            0, lambda: self._push_expose_command(names, exposed))

    def _push_expose_command(self, names, exposed):
        if self.graph is None:
            return
        self.stack.push(commands.SetExposeCommand(
            self.graph, names, exposed))

    def _commit_merged(self, input_name, value):
        if self.node is None:
            return
        self.stack.push(commands.SetValueCommand(
            self.graph, self.node.name, input_name, value), merge=True)

    # ----------------------------------------------------------------- misc

    def _placeholder(self):
        label = QtWidgets.QLabel("Select a node to edit its properties.")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setStyleSheet("color: #8a8a8f;")
        self.scroll.setWidget(label)


def _scalar(value, fallback):
    if isinstance(value, (int, float)):
        return float(value)
    return fallback
