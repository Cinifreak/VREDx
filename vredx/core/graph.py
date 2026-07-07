# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Pure-Python MaterialX graph document model.

A :class:`Graph` is the single source of truth edited by the UI and
serialized by :mod:`vredx.core.mtlx_writer`.  It knows nothing about Qt
or VRED, which keeps it trivially unit-testable.

Structure mirrors a MaterialX document:

* nodes live in an implicit nodegraph, except shader/material-semantic
  nodes (surfaceshader, material, ...) which sit at document level;
  the writer decides placement, the model does not care.
* every node is an instance of a :class:`NodeDef` from the library, or
  an *opaque* node (unknown definition preserved from an imported file).
"""

import itertools
import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from . import mtlx_types
from .nodedef_library import InputDef, NodeDef, OutputDef


class GraphError(Exception):
    """Raised for illegal graph operations (bad connect, unknown port...)."""


@dataclass
class Edge:
    """A connection: (src node, src output) -> (dst node, dst input)."""
    src_node: str
    src_output: str
    dst_node: str
    dst_input: str

    def key(self) -> Tuple[str, str]:
        """Input ports accept at most one edge; this is that identity."""
        return (self.dst_node, self.dst_input)


@dataclass
class CompoundOutput:
    """A named output port on a compound :class:`NodeGraph`."""
    name: str
    type: str
    internal_node: str
    internal_output: str = "out"


class Node:
    """An instance of a MaterialX node in the document."""

    def __init__(self, name: str, nodedef: NodeDef,
                 position: Tuple[float, float] = (0.0, 0.0),
                 opaque: bool = False):
        self.name = name
        self.nodedef = nodedef
        self.position = position
        self.opaque = opaque            # unknown def preserved from import
        # Parent compound nodegraph name, or None for document-root nodes.
        self.compound: Optional[str] = None
        # True for the group node shown at the parent scope (not a real op).
        self.is_compound: bool = False
        # Literal values overriding nodedef defaults, by input name.
        self.values: Dict[str, object] = {}
        # Raw XML attributes preserved for opaque nodes (round-trip).
        self.extra_attrs: Dict[str, str] = {}
        # Extra per-input XML attributes (colorspace, channels, unit...)
        # preserved for round-trip: {input_name: {attr: value}}.
        self.input_attrs: Dict[str, Dict[str, str]] = {}
        # When True, literal inputs are written without uivisible="false" so
        # VRED shows this node in its Realistic material editor.
        self.expose_in_material = False

    # ------------------------------------------------------------ inputs

    @property
    def category(self) -> str:
        return self.nodedef.node

    @property
    def output_type(self) -> str:
        return self.nodedef.output_type

    def input_def(self, name: str) -> InputDef:
        idef = self.nodedef.find_input(name)
        if idef is None:
            raise GraphError("Node '%s' has no input '%s'" % (self.name, name))
        return idef

    def output_def(self, name: str) -> OutputDef:
        odef = self.nodedef.find_output(name)
        if odef is None:
            raise GraphError("Node '%s' has no output '%s'" % (self.name, name))
        return odef

    def get_value(self, input_name: str):
        """Effective literal value: explicit override or nodedef default."""
        if input_name in self.values:
            return self.values[input_name]
        return self.input_def(input_name).value

    def set_value(self, input_name: str, value):
        self.input_def(input_name)  # validate the input exists
        self.values[input_name] = value

    def clear_value(self, input_name: str):
        self.values.pop(input_name, None)

    def is_shader_semantic(self) -> bool:
        return mtlx_types.is_shader_type(self.output_type)


class Graph:
    """The editable document: nodes + edges + document metadata."""

    def __init__(self, name: str = "vredx_material"):
        self.name = name
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        # Compound nodegraph metadata: name -> exported output ports.
        self.compounds: Dict[str, List[CompoundOutput]] = {}
        self.colorspace = "lin_rec709"
        # Directory of the .mtlx file this graph was loaded from or last
        # saved to; used to resolve relative texture paths.
        self.document_dir = ""
        # Temp folder when the graph was loaded from a .zip archive.
        self.temp_extract_dir = ""
        # Absolute path of the .mtlx file backing this graph, if any.
        self.source_mtlx_path = ""

    # ------------------------------------------------------------- nodes

    def add_node(self, nodedef: NodeDef, name: Optional[str] = None,
                 position: Tuple[float, float] = (0.0, 0.0),
                 opaque: bool = False,
                 compound: Optional[str] = None,
                 is_compound: bool = False) -> Node:
        node = Node(self.unique_name(name or nodedef.node),
                    nodedef, position, opaque)
        node.compound = compound
        node.is_compound = is_compound
        self.nodes[node.name] = node
        return node

    def compound_member_count(self, compound_name: str) -> int:
        """Number of internal nodes inside a compound nodegraph."""
        return sum(1 for node in self.nodes.values()
                   if node.compound == compound_name and not node.is_compound)

    def compound_export_outputs(self, compound_name: str,
                                node_name: str) -> List[str]:
        """Exported output port names driven by *node_name* inside a compound."""
        return [output.name for output in self.compounds.get(compound_name, ())
                if output.internal_node == node_name]

    def is_compound_export_node(self, compound_name: str,
                                node_name: str) -> bool:
        return bool(self.compound_export_outputs(compound_name, node_name))

    def compound_proxy(self, compound_name: str) -> Node:
        node = self.node(compound_name)
        if not node.is_compound:
            raise GraphError("'%s' is not a compound nodegraph" % compound_name)
        return node

    def unique_compound_output_name(self, compound_name: str,
                                    base: str) -> str:
        base = _sanitize_name(base)
        existing = {o.name for o in self.compounds.get(compound_name, ())}
        if base not in existing:
            return base
        stem = re.sub(r"\d+$", "", base) or base
        for i in itertools.count(1):
            candidate = "%s%d" % (stem, i)
            if candidate not in existing:
                return candidate
        raise AssertionError("unreachable")

    def refresh_compound_proxy(self, compound_name: str) -> None:
        """Rebuild the compound group node's interface ports."""
        proxy = self.compound_proxy(compound_name)
        outputs = self.compounds.get(compound_name, [])
        proxy.nodedef = make_compound_nodedef(compound_name, outputs)

    def add_compound_output(self, compound_name: str, output_name: str,
                            internal_node: str,
                            internal_output: str = "out") -> CompoundOutput:
        """Expose an internal node port on the compound group node."""
        if compound_name not in self.compounds:
            raise GraphError("Unknown compound '%s'" % compound_name)
        node = self.node(internal_node)
        if node.compound != compound_name:
            raise GraphError(
                "Node '%s' is not inside compound '%s'"
                % (internal_node, compound_name))
        odef = node.output_def(internal_output)
        names = {o.name for o in self.compounds[compound_name]}
        if output_name in names:
            raise GraphError(
                "Compound output '%s' already exists" % output_name)
        entry = CompoundOutput(
            name=output_name, type=odef.type,
            internal_node=internal_node,
            internal_output=internal_output)
        self.compounds[compound_name].append(entry)
        self.refresh_compound_proxy(compound_name)
        return entry

    def remove_compound_output(self, compound_name: str,
                               output_name: str) -> Tuple[CompoundOutput, List[Edge]]:
        """Remove a compound export and disconnect its external edges."""
        outputs = self.compounds.get(compound_name)
        if outputs is None:
            raise GraphError("Unknown compound '%s'" % compound_name)
        match = None
        kept = []
        for output in outputs:
            if output.name == output_name:
                match = output
            else:
                kept.append(output)
        if match is None:
            raise GraphError(
                "Compound '%s' has no output '%s'"
                % (compound_name, output_name))
        self.compounds[compound_name] = kept
        removed = [e for e in self.edges
                   if e.src_node == compound_name
                   and e.src_output == output_name]
        self.edges = [e for e in self.edges if e not in removed]
        self.refresh_compound_proxy(compound_name)
        return match, removed

    def create_compound(self, name: str, member_names: List[str],
                        position: Tuple[float, float] = (0.0, 0.0)
                        ) -> Tuple[Node, dict]:
        """Group *member_names* into a new compound nodegraph at document root.

        Returns the compound proxy node and a snapshot dict for undo.
        Outgoing edges crossing the new boundary are re-routed through
        auto-created compound outputs; incoming edges are removed.
        """
        members = sorted(set(member_names))
        if len(members) < 1:
            raise GraphError("Select at least one node for a compound graph")
        for member in members:
            node = self.node(member)
            if node.is_compound:
                raise GraphError(
                    "Cannot nest compound node '%s' inside another"
                    % member)
            if node.compound is not None:
                raise GraphError(
                    "Node '%s' is already inside compound '%s'"
                    % (member, node.compound))

        compound_name = self.unique_name(_sanitize_name(name))
        member_set = set(members)
        state = {
            "compound_name": compound_name,
            "members": members,
            "prior_compound": {m: None for m in members},
            "removed_edges": [],
            "rewired_edges": [],
        }

        self.compounds[compound_name] = []
        proxy = self.add_node(
            make_compound_nodedef(compound_name, []),
            name=compound_name, position=position, is_compound=True)
        for member in members:
            self.nodes[member].compound = compound_name

        promoted: Dict[Tuple[str, str], str] = {}
        for edge in list(self.edges):
            src_inside = edge.src_node in member_set
            dst_inside = edge.dst_node in member_set
            if src_inside and not dst_inside:
                key = (edge.src_node, edge.src_output)
                if key not in promoted:
                    out_name = self.unique_compound_output_name(
                        compound_name,
                        "%s_%s" % (edge.src_node, edge.src_output))
                    self.add_compound_output(
                        compound_name, out_name, key[0], key[1])
                    promoted[key] = out_name
                state["rewired_edges"].append(
                    (edge, edge.src_node, edge.src_output))
                edge.src_node = compound_name
                edge.src_output = promoted[key]
            elif dst_inside and not src_inside:
                state["removed_edges"].append(edge)
                self.edges.remove(edge)

        state["outputs"] = list(self.compounds[compound_name])
        state["proxy_position"] = position
        return proxy, state

    def reapply_create_compound(self, state: dict) -> None:
        """Re-apply a compound creation after undo."""
        compound_name = state["compound_name"]
        outputs = list(state["outputs"])
        self.compounds[compound_name] = outputs
        nodedef = make_compound_nodedef(compound_name, outputs)
        if compound_name in self.nodes:
            proxy = self.nodes[compound_name]
            proxy.nodedef = nodedef
            proxy.is_compound = True
            proxy.compound = None
        else:
            self.add_node(nodedef, name=compound_name,
                          position=state["proxy_position"],
                          is_compound=True)
        for member in state["members"]:
            self.node(member).compound = compound_name
        for edge, old_src, old_output in state["rewired_edges"]:
            out_name = next(
                o.name for o in outputs
                if o.internal_node == old_src
                and o.internal_output == old_output)
            edge.src_node = compound_name
            edge.src_output = out_name
        for edge in state["removed_edges"]:
            if edge in self.edges:
                self.edges.remove(edge)

    def undo_create_compound(self, state: dict) -> None:
        """Revert :meth:`create_compound`."""
        compound_name = state["compound_name"]
        for member in state["members"]:
            self.node(member).compound = state["prior_compound"][member]
        for edge, old_src, old_output in state["rewired_edges"]:
            edge.src_node = old_src
            edge.src_output = old_output
        self.edges.extend(state["removed_edges"])
        if compound_name in self.compounds:
            del self.compounds[compound_name]
        if compound_name in self.nodes:
            del self.nodes[compound_name]

    def dissolve_compound(self, compound_name: str) -> dict:
        """Ungroup a compound nodegraph back onto the document root."""
        if compound_name not in self.compounds:
            raise GraphError("Unknown compound '%s'" % compound_name)
        proxy = self.compound_proxy(compound_name)
        members = sorted(
            n.name for n in self.nodes.values()
            if n.compound == compound_name and not n.is_compound)
        outputs = list(self.compounds[compound_name])
        state = {
            "compound_name": compound_name,
            "members": members,
            "outputs": outputs,
            "proxy_position": proxy.position,
            "rewired_edges": [],
        }
        output_by_name = {o.name: o for o in outputs}
        for edge in list(self.edges):
            if edge.src_node != compound_name:
                continue
            output = output_by_name.get(edge.src_output)
            if output is None:
                continue
            state["rewired_edges"].append(
                (edge, edge.src_node, edge.src_output))
            edge.src_node = output.internal_node
            edge.src_output = output.internal_output
        for member in members:
            self.nodes[member].compound = None
        del self.compounds[compound_name]
        del self.nodes[compound_name]
        from . import mtlx_paths
        root_names = self.nodes_in_scope(None)
        state["pre_layout_positions"] = {
            name: tuple(self.node(name).position) for name in root_names}
        mtlx_paths._layout_scope(self, None)
        return state

    def apply_dissolve_compound(self, state: dict) -> None:
        """Re-apply :meth:`dissolve_compound` after undo."""
        compound_name = state["compound_name"]
        output_by_name = {o.name: o for o in state["outputs"]}
        for edge, _compound, output_name in state["rewired_edges"]:
            output = output_by_name[output_name]
            edge.src_node = output.internal_node
            edge.src_output = output.internal_output
        for member in state["members"]:
            self.node(member).compound = None
        if compound_name in self.compounds:
            del self.compounds[compound_name]
        if compound_name in self.nodes:
            del self.nodes[compound_name]
        from . import mtlx_paths
        root_names = self.nodes_in_scope(None)
        state["pre_layout_positions"] = {
            name: tuple(self.node(name).position) for name in root_names}
        mtlx_paths._layout_scope(self, None)

    def undo_dissolve_compound(self, state: dict) -> None:
        """Restore a dissolved compound nodegraph."""
        create_state = {
            "compound_name": state["compound_name"],
            "members": state["members"],
            "outputs": list(state["outputs"]),
            "proxy_position": state["proxy_position"],
            "prior_compound": {m: None for m in state["members"]},
            "removed_edges": [],
            "rewired_edges": [],
        }
        output_by_name = {o.name: o for o in state["outputs"]}
        for edge, _compound, output_name in state["rewired_edges"]:
            output = output_by_name[output_name]
            create_state["rewired_edges"].append(
                (edge, output.internal_node, output.internal_output))
        self.reapply_create_compound(create_state)
        if "pre_layout_positions" in state:
            self.restore_layout_positions(state["pre_layout_positions"])

    def restore_layout_positions(self, positions: Dict[str, Tuple[float, float]]):
        """Restore node positions captured before an auto-layout pass."""
        for name, pos in positions.items():
            if name in self.nodes:
                self.nodes[name].position = pos

    def _sync_compound_outputs_after_node_removed(self, name: str) -> None:
        for compound_name in list(self.compounds):
            before = len(self.compounds[compound_name])
            self.compounds[compound_name] = [
                o for o in self.compounds[compound_name]
                if o.internal_node != name]
            if len(self.compounds[compound_name]) != before:
                self.refresh_compound_proxy(compound_name)

    def _sync_compound_outputs_after_node_renamed(self, old: str, new: str):
        for compound_name, outputs in self.compounds.items():
            changed = False
            for output in outputs:
                if output.internal_node == old:
                    output.internal_node = new
                    changed = True
            if changed:
                self.refresh_compound_proxy(compound_name)

    def nodes_in_scope(self, scope: Optional[str] = None) -> List[str]:
        """Node names visible at *scope* (``None`` = document root)."""
        names: List[str] = []
        for name, node in self.nodes.items():
            if scope is None:
                if node.compound is None:
                    names.append(name)
            elif node.compound == scope and not node.is_compound:
                names.append(name)
        return sorted(names)

    def edge_in_scope(self, edge: Edge, scope: Optional[str] = None) -> bool:
        visible = set(self.nodes_in_scope(scope))
        return edge.src_node in visible and edge.dst_node in visible

    def resolve_edge_source(self, edge: Edge) -> Tuple[str, str]:
        """Follow compound proxy outputs to the internal source node."""
        src = self.node(edge.src_node)
        if not src.is_compound:
            return edge.src_node, edge.src_output
        for output in self.compounds.get(src.name, ()):
            if output.name == edge.src_output:
                return output.internal_node, output.internal_output
        return edge.src_node, edge.src_output

    def remove_node(self, name: str) -> Tuple[Node, List[Edge]]:
        """Remove a node and all its edges.  Returns them for undo."""
        node = self.node(name)
        removed = [e for e in self.edges
                   if e.src_node == name or e.dst_node == name]
        self.edges = [e for e in self.edges if e not in removed]
        del self.nodes[name]
        self._sync_compound_outputs_after_node_removed(name)
        return node, removed

    def restore_node(self, node: Node, edges: List[Edge]):
        if node.name in self.nodes:
            raise GraphError("Node name '%s' already in use" % node.name)
        self.nodes[node.name] = node
        self.edges.extend(edges)

    def rename_node(self, old: str, new: str) -> str:
        node = self.node(old)
        new = self.unique_name(new)
        del self.nodes[old]
        node.name = new
        self.nodes[new] = node
        for e in self.edges:
            if e.src_node == old:
                e.src_node = new
            if e.dst_node == old:
                e.dst_node = new
        self._sync_compound_outputs_after_node_renamed(old, new)
        return new

    def node(self, name: str) -> Node:
        try:
            return self.nodes[name]
        except KeyError:
            raise GraphError("No node named '%s'" % name)

    def unique_name(self, base: str) -> str:
        base = _sanitize_name(base)
        if base not in self.nodes:
            return base
        stem = re.sub(r"\d+$", "", base) or base
        for i in itertools.count(1):
            candidate = "%s%d" % (stem, i)
            if candidate not in self.nodes:
                return candidate
        raise AssertionError("unreachable")

    # ------------------------------------------------------------- edges

    def can_connect(self, src_node: str, src_output: str,
                    dst_node: str, dst_input: str) -> Tuple[bool, str]:
        """Check legality; returns (ok, reason-if-not)."""
        if src_node == dst_node:
            return False, "Cannot connect a node to itself"
        try:
            src = self.node(src_node)
            dst = self.node(dst_node)
            odef = src.output_def(src_output)
            idef = dst.input_def(dst_input)
        except GraphError as exc:
            return False, str(exc)
        if not mtlx_types.types_compatible(odef.type, idef.type):
            return False, ("Type mismatch: %s output cannot drive %s input"
                           % (odef.type, idef.type))
        if self._creates_cycle(src_node, dst_node):
            return False, "Connection would create a cycle"
        return True, ""

    def connect(self, src_node: str, src_output: str,
                dst_node: str, dst_input: str) -> Tuple[Edge, Optional[Edge]]:
        """Create an edge.  Returns (new edge, displaced edge or None)."""
        ok, reason = self.can_connect(src_node, src_output, dst_node, dst_input)
        if not ok:
            raise GraphError(reason)
        edge = Edge(src_node, src_output, dst_node, dst_input)
        displaced = self.edge_into(dst_node, dst_input)
        if displaced is not None:
            self.edges.remove(displaced)
        self.edges.append(edge)
        return edge, displaced

    def disconnect(self, edge: Edge):
        try:
            self.edges.remove(edge)
        except ValueError:
            # match by value, the UI may hold a different instance
            for e in list(self.edges):
                if (e.src_node, e.src_output, e.dst_node, e.dst_input) == \
                        (edge.src_node, edge.src_output, edge.dst_node, edge.dst_input):
                    self.edges.remove(e)
                    return
            raise GraphError("Edge not found")

    def edge_into(self, dst_node: str, dst_input: str) -> Optional[Edge]:
        for e in self.edges:
            if e.dst_node == dst_node and e.dst_input == dst_input:
                return e
        return None

    def edges_from(self, src_node: str) -> List[Edge]:
        return [e for e in self.edges if e.src_node == src_node]

    def edges_of(self, node_name: str) -> List[Edge]:
        return [e for e in self.edges
                if e.src_node == node_name or e.dst_node == node_name]

    def _creates_cycle(self, src_node: str, dst_node: str) -> bool:
        """Would src->dst close a loop?  True if src is reachable from dst."""
        seen = set()
        stack = [dst_node]
        while stack:
            current = stack.pop()
            if current == src_node:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(e.dst_node for e in self.edges
                         if e.src_node == current)
        return False

    # --------------------------------------------------------- traversal

    def upstream(self, node_name: str) -> Iterator[Node]:
        """All nodes feeding into node_name (depth-first, deduplicated)."""
        seen = set()
        stack = [node_name]
        while stack:
            current = stack.pop()
            for e in self.edges:
                if e.dst_node == current and e.src_node not in seen:
                    seen.add(e.src_node)
                    stack.append(e.src_node)
                    yield self.nodes[e.src_node]

    def material_nodes(self) -> List[Node]:
        return [n for n in self.nodes.values()
                if n.output_type == "material"]

    def surface_shader_nodes(self) -> List[Node]:
        return [n for n in self.nodes.values()
                if n.output_type == "surfaceshader"]

    def topological_order(self) -> List[Node]:
        """Nodes sorted so that every edge goes from earlier to later."""
        indegree = {name: 0 for name in self.nodes}
        for e in self.edges:
            if e.dst_node in indegree:
                indegree[e.dst_node] += 1
        ready = sorted(n for n, d in indegree.items() if d == 0)
        order: List[Node] = []
        while ready:
            name = ready.pop(0)
            order.append(self.nodes[name])
            for e in sorted(self.edges_from(name),
                            key=lambda e: (e.dst_node, e.dst_input)):
                indegree[e.dst_node] -= 1
                if indegree[e.dst_node] == 0:
                    ready.append(e.dst_node)
            ready.sort()
        if len(order) != len(self.nodes):
            raise GraphError("Graph contains a cycle")
        return order


def connected_inputs(graph: Graph, node_name: str) -> set:
    """Input port names on *node_name* that have an incoming edge."""
    return {e.dst_input for e in graph.edges if e.dst_node == node_name}


def material_ui_inputs(node: Node, connected: set) -> Iterator[str]:
    """Unconnected, non-shader inputs VRED can show in the material editor."""
    for idef in node.nodedef.inputs:
        if idef.name in connected:
            continue
        if mtlx_types.is_shader_type(idef.type):
            continue
        yield idef.name


def exposable_literal_inputs(node: Node, graph: Graph) -> Iterator[str]:
    """Literal inputs that may be written with uivisible for VRED."""
    connected = connected_inputs(graph, node.name)
    for idef in node.nodedef.inputs:
        if idef.name in connected:
            continue
        if mtlx_types.is_shader_type(idef.type):
            continue
        yield idef.name


def can_expose_in_material(node: Node, graph: Graph) -> bool:
    """Whether the inspector may offer an 'Expose in material' toggle."""
    if node.is_shader_semantic() or node.is_compound:
        return False
    if any(True for _ in exposable_literal_inputs(node, graph)):
        return True
    # Nested pattern nodes are often fully wired internally but still
    # need literal parameters promoted to VRED's material editor.
    if node.compound is not None:
        return any(not mtlx_types.is_shader_type(idef.type)
                   for idef in node.nodedef.inputs)
    return False


def infer_expose_in_material(node: Node, graph: Graph) -> bool:
    """Derive expose flag from uivisible attributes on imported inputs."""
    if not can_expose_in_material(node, graph):
        return False
    connected = connected_inputs(graph, node.name)
    written = [name for name in material_ui_inputs(node, connected)
               if name in node.values or name in node.input_attrs]
    if not written:
        return False
    return any(node.input_attrs.get(name, {}).get("uivisible") != "false"
               for name in written)


def expose_check_state(nodes, graph):
    """Check-state label for a selection's expose-in-material toggle.

    Returns ``None`` when no selected node supports the toggle, otherwise
    one of ``"checked"``, ``"unchecked"``, or ``"partial"``.
    """
    targets = [n for n in nodes if can_expose_in_material(n, graph)]
    if not targets:
        return None
    states = [n.expose_in_material for n in targets]
    if all(states):
        return "checked"
    if not any(states):
        return "unchecked"
    return "partial"


def sync_expose_in_material(graph: Graph) -> None:
    """Set :attr:`Node.expose_in_material` on every node after import."""
    for node in graph.nodes.values():
        node.expose_in_material = infer_expose_in_material(node, graph)


def _sanitize_name(name: str) -> str:
    """MaterialX element names: alphanumerics and underscores only."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
    if not name or name[0].isdigit():
        name = "n_" + name
    return name


def make_compound_nodedef(name: str,
                          outputs: List[CompoundOutput]) -> NodeDef:
    """Synthesize a NodeDef for a compound nodegraph group node."""
    return NodeDef(
        name="COMPOUND_%s" % name,
        node="nodegraph",
        nodegroup="organization",
        doc="Compound nodegraph '%s'." % name,
        inputs=[],
        outputs=[OutputDef(name=o.name, type=o.type) for o in outputs],
    )


def make_opaque_nodedef(category: str, output_type: str,
                        inputs: List[InputDef]) -> NodeDef:
    """Synthesize a NodeDef for a node whose definition is unknown.

    Used by the reader so that documents containing custom or newer nodes
    still open (with warnings) instead of failing.
    """
    return NodeDef(
        name="OPAQUE_%s_%s" % (category, output_type),
        node=category,
        nodegroup="unknown",
        doc="Unknown node definition preserved from imported document.",
        inputs=inputs,
        outputs=[OutputDef(name="out", type=output_type)],
    )
