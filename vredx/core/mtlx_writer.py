# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Serialize a :class:`vredx.core.graph.Graph` to a MaterialX 1.39 document.

When the graph contains compound nodegraphs, nested ``<nodegraph>`` blocks
are written with internal nodes and ``<output>`` indirections so hierarchy
survives save/load round-trips.  Flat graphs (no compounds) are written as
direct children of the ``<materialx>`` root.

Determinism: nodes are emitted in topological order (ties broken by
name) and only explicitly-set input values are written, so identical
graphs always produce byte-identical documents - which the test suite
relies on for golden-file comparison.

Node editor positions are stored as ``xpos``/``ypos`` attributes, the
same convention the MaterialX Graph Editor uses, so layout survives a
save/load round-trip and remains compatible with other tools.
"""

import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

from . import mtlx_paths, mtlx_types
from .graph import Graph, can_expose_in_material

MATERIALX_VERSION = "1.39"

# xpos/ypos are stored in abstract grid units in other tools; scale scene
# pixels down so documents look sane in the MaterialX Graph Editor too.
POSITION_SCALE = 0.01


def write_document(graph: Graph, output_path: str = None) -> str:
    """Serialize the graph to a MaterialX XML string."""
    filename_overrides = {}
    if output_path:
        filename_overrides = mtlx_paths.stage_textures_for_output(
            graph, output_path)
    root = ET.Element("materialx")
    root.set("version", MATERIALX_VERSION)
    if graph.colorspace:
        root.set("colorspace", graph.colorspace)

    for compound_name in sorted(graph.compounds.keys()):
        _write_nodegraph(graph, root, compound_name, filename_overrides)

    for node in _root_emit_order(graph):
        elem = ET.SubElement(root, node.category)
        elem.set("name", node.name)
        elem.set("type", _element_type(node))
        _write_position(elem, node)
        _write_node_attrs(node, elem)
        _write_inputs(graph, node, elem, scope=None,
                      filename_overrides=filename_overrides.get(node.name))

    return _pretty(root)


def save_document(graph: Graph, path: str):
    text = write_document(graph, output_path=path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    graph.document_dir = os.path.dirname(os.path.abspath(path))


# ----------------------------------------------------------------- helpers

def _write_nodegraph(graph: Graph, root, compound_name: str,
                     filename_overrides):
    ng_elem = ET.SubElement(root, "nodegraph")
    ng_elem.set("name", compound_name)
    for iface in graph.compound_inputs.get(compound_name, ()):
        inp_elem = ET.SubElement(ng_elem, "input")
        inp_elem.set("name", iface.name)
        inp_elem.set("type", iface.type)
        if iface.value is not None:
            inp_elem.set("value",
                         mtlx_types.format_value(iface.type, iface.value))
        for key, value in sorted(iface.attrs.items()):
            inp_elem.set(key, value)
    for node in _member_emit_order(graph, compound_name):
        elem = ET.SubElement(ng_elem, node.category)
        elem.set("name", node.name)
        elem.set("type", _element_type(node))
        _write_position(elem, node)
        _write_node_attrs(node, elem)
        _write_inputs(graph, node, elem, scope=compound_name,
                      filename_overrides=filename_overrides.get(node.name))
    for output in graph.compounds.get(compound_name, ()):
        out_elem = ET.SubElement(ng_elem, "output")
        out_elem.set("name", output.name)
        out_elem.set("type", output.type)
        if output.interfacename:
            out_elem.set("interfacename", output.interfacename)
        else:
            out_elem.set("nodename", output.internal_node)
            src = graph.node(output.internal_node)
            if (len(src.nodedef.outputs) > 1
                    or output.internal_output != "out"):
                out_elem.set("output", output.internal_output)


def _root_emit_order(graph: Graph):
    """Topological order of document-root nodes (not compound members)."""
    order = [n for n in graph.topological_order()
             if n.compound is None and not n.is_compound]
    return sorted(order, key=lambda n: (
        _semantic_rank(n.output_type), order.index(n)))


def _member_emit_order(graph: Graph, compound_name: str):
    """Topological order of nodes inside a compound nodegraph."""
    members = set(graph.nodes_in_scope(compound_name))
    order = [n for n in graph.topological_order() if n.name in members]
    return sorted(order, key=lambda n: order.index(n))


def _semantic_rank(output_type: str) -> int:
    if output_type == "material":
        return 2
    if mtlx_types.is_shader_type(output_type):
        return 1
    return 0


def _element_type(node) -> str:
    """MaterialX element type attribute (multi-output nodes use multioutput)."""
    if len(node.nodedef.outputs) > 1:
        return "multioutput"
    return node.output_type


def _write_node_attrs(node, elem):
    for key, value in sorted(node.extra_attrs.items()):
        if key not in ("name", "type", "xpos", "ypos"):
            elem.set(key, value)


def _write_position(elem, node):
    x, y = node.position
    if x or y:
        elem.set("xpos", _fmt_pos(x * POSITION_SCALE))
        elem.set("ypos", _fmt_pos(y * POSITION_SCALE))


def _fmt_pos(v: float) -> str:
    return ("%.6f" % v).rstrip("0").rstrip(".")


def _write_inputs(graph: Graph, node, elem, scope, filename_overrides=None):
    """Emit one <input> per connection or explicit value override."""
    filename_overrides = filename_overrides or {}
    connected = {}
    for edge in graph.edges:
        if edge.dst_node == node.name:
            connected[edge.dst_input] = edge

    ordered_names = [i.name for i in node.nodedef.inputs]
    extra = sorted(set(list(node.values) + list(connected)) -
                   set(ordered_names))
    for input_name in ordered_names + extra:
        edge = connected.get(input_name)
        has_value = input_name in node.values
        idef = node.nodedef.find_input(input_name)
        input_type = idef.type if idef else "float"
        attrs = dict(node.input_attrs.get(input_name, {}))
        iface = attrs.pop("interfacename", None)
        if iface:
            inp = ET.SubElement(elem, "input")
            inp.set("name", input_name)
            inp.set("type", input_type)
            inp.set("interfacename", iface)
            for key, value in sorted(attrs.items()):
                if key not in ("name", "type", "value", "nodename", "output",
                               "nodegraph", "interfacename"):
                    inp.set(key, value)
            continue
        if (edge is None and idef and idef.defaultgeomprop
                and input_name not in node.values):
            continue
        write_literal = edge is None and (
            has_value or _write_exposed_default(node, input_name, idef))
        if edge is None and write_literal:
            literal = filename_overrides.get(
                input_name, node.get_value(input_name))
            if literal is None:
                write_literal = False
        if edge is None and not write_literal:
            continue

        inp = ET.SubElement(elem, "input")
        inp.set("name", input_name)
        inp.set("type", input_type)

        if edge is not None:
            _write_connection(graph, inp, edge, scope)
        else:
            value = filename_overrides.get(input_name, node.get_value(input_name))
            inp.set("value",
                    mtlx_types.format_value(input_type, value))

        if edge is None and can_expose_in_material(node, graph):
            if node.expose_in_material:
                attrs.pop("uivisible", None)
            else:
                attrs["uivisible"] = "false"
        for key, value in sorted(attrs.items()):
            if key not in ("name", "type", "value", "nodename", "output",
                           "nodegraph", "interfacename"):
                inp.set(key, value)


def _write_exposed_default(node, input_name, idef) -> bool:
    """Write nodedef defaults for exposed nested literals not yet overridden."""
    if not node.expose_in_material or idef is None:
        return False
    if mtlx_types.is_shader_type(idef.type):
        return False
    return input_name in {i.name for i in node.nodedef.inputs}


def _write_connection(graph: Graph, inp, edge, scope):
    src = graph.node(edge.src_node)
    src_output = edge.src_output
    if src.is_compound:
        inp.set("nodegraph", edge.src_node)
        inp.set("output", src_output)
    elif scope is not None and src.compound == scope:
        inp.set("nodename", edge.src_node)
        if len(src.nodedef.outputs) > 1 or src_output != "out":
            inp.set("output", src_output)
    else:
        inp.set("nodename", edge.src_node)
        if len(src.nodedef.outputs) > 1 or src_output != "out":
            inp.set("output", src_output)


def _pretty(root) -> str:
    raw = ET.tostring(root, encoding="unicode")
    text = minidom.parseString(raw).toprettyxml(indent="  ")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0"?>'
    return "\n".join(lines) + "\n"
