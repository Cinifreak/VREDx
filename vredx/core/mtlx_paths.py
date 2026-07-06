# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Auto-layout for imported MaterialX graphs without editor positions."""

from typing import Dict, List, Tuple

from .graph import Graph, GraphError, Node


def auto_layout_nodes(graph: Graph,
                      spacing: Tuple[float, float] = (300.0, 160.0)) -> None:
    """Place imported nodes left-to-right, surface shader then material on the right."""
    try:
        order = graph.topological_order()
    except GraphError:
        order = sorted(graph.nodes.values(), key=lambda n: n.name)
    if len(order) <= 1:
        if order:
            order[0].position = (0.0, 0.0)
        return

    spacing_x, spacing_y = spacing
    depths = _node_depths(graph, order)
    surfaces = [n for n in order if n.output_type == "surfaceshader"]
    materials = [n for n in order if n.output_type == "material"]
    pinned = {n.name for n in surfaces + materials}
    middle = [n for n in order if n.name not in pinned]

    max_middle_depth = max((depths[n.name] for n in middle), default=-1)
    surface_col = max_middle_depth + 1
    material_col = max_middle_depth + 2

    rows_by_depth: Dict[int, List[Node]] = {}
    for node in middle:
        rows_by_depth.setdefault(depths[node.name], []).append(node)
    for depth in rows_by_depth:
        rows_by_depth[depth].sort(key=lambda n: n.name)
        for row, node in enumerate(rows_by_depth[depth]):
            node.position = (depth * spacing_x, row * spacing_y)

    surface_for_material = {}
    for material in materials:
        edge = graph.edge_into(material.name, "surfaceshader")
        if edge is not None:
            surface_for_material[material.name] = edge.src_node

    assigned = set()
    row = 0
    for material in sorted(materials, key=lambda n: n.name):
        surf_name = surface_for_material.get(material.name)
        if surf_name is None or surf_name in assigned:
            continue
        surface = graph.node(surf_name)
        y = row * spacing_y
        surface.position = (surface_col * spacing_x, y)
        material.position = (material_col * spacing_x, y)
        assigned.add(surf_name)
        assigned.add(material.name)
        row += 1

    for surface in sorted(surfaces, key=lambda n: n.name):
        if surface.name in assigned:
            continue
        surface.position = (surface_col * spacing_x, row * spacing_y)
        assigned.add(surface.name)
        row += 1

    for material in sorted(materials, key=lambda n: n.name):
        if material.name in assigned:
            continue
        material.position = (material_col * spacing_x, row * spacing_y)
        assigned.add(material.name)
        row += 1


def _node_depths(graph: Graph, order: List[Node]) -> Dict[str, int]:
    """Longest-path depth from graph sources (left-to-right layering)."""
    preds = {name: [] for name in graph.nodes}
    for edge in graph.edges:
        preds[edge.dst_node].append(edge.src_node)
    depths = {}
    for node in order:
        upstream = preds.get(node.name) or []
        depths[node.name] = max((depths[src] for src in upstream), default=-1) + 1
    return depths
