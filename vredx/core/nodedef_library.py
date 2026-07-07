# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Parse the MaterialX node definition libraries shipped with VRED.

The node palette is generated from these files so that it exactly matches
what the **local VRED installation** can compile.  Sources, in priority
order:

1. ``VRED_ROOT`` (set by VRED at runtime) →
   ``runtimeData/MaterialX/libraries``
2. The snapshot bundled with the plugin at ``VredX/resources/libraries``
   (development and pytest only, when ``VRED_ROOT`` is unset)

Only ``xml.etree`` is used - no PyMaterialX dependency.
"""

import glob
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import mtlx_types

# Input types that are configuration metadata, not stream connections.
_CONFIG_INPUT_TYPES = frozenset({"string", "filename", "geomname"})

# Library files that define nodes usable in an authored document.  The
# generator implementation files (*_impl.mtlx) and target defs are skipped.
_DEF_FILE_PATTERNS = (
    os.path.join("stdlib", "stdlib_defs.mtlx"),
    os.path.join("pbrlib", "pbrlib_defs.mtlx"),
    os.path.join("nprlib", "nprlib_defs.mtlx"),
    os.path.join("cmlib", "cmlib_defs.mtlx"),
    os.path.join("bxdf", "*.mtlx"),
    os.path.join("bxdf", "lama", "*.mtlx"),
)


@dataclass
class InputDef:
    name: str
    type: str
    value: object = None           # parsed python value (None if unset)
    uiname: str = ""
    uifolder: str = ""
    uimin: object = None
    uimax: object = None
    uisoftmin: object = None
    uisoftmax: object = None
    enum_values: Tuple[str, ...] = ()
    uniform: bool = False
    advanced: bool = False
    defaultgeomprop: str = ""
    doc: str = ""


@dataclass
class OutputDef:
    name: str
    type: str


@dataclass
class NodeDef:
    """A single MaterialX <nodedef> (one type signature of a node)."""
    name: str                       # e.g. "ND_image_color3"
    node: str                       # e.g. "image" (the node category)
    nodegroup: str = ""             # e.g. "texture2d", "pbr", "shader"
    doc: str = ""
    version: str = ""
    is_default_version: bool = True
    inherit: str = ""
    library: str = ""               # e.g. "stdlib", "pbrlib", "bxdf"
    source_file: str = ""
    inputs: List[InputDef] = field(default_factory=list)
    outputs: List[OutputDef] = field(default_factory=list)

    @property
    def output_type(self) -> str:
        return self.outputs[0].type if self.outputs else "none"

    def connection_input_types(self) -> Tuple[str, ...]:
        """Distinct connectable input types, in declaration order."""
        seen = set()
        types: List[str] = []
        for idef in self.inputs:
            if idef.type in _CONFIG_INPUT_TYPES:
                continue
            if idef.type in seen:
                continue
            seen.add(idef.type)
            types.append(idef.type)
        return tuple(types)

    def type_signature(self) -> str:
        """Compact label for type variants, e.g. ``float → vector3``."""
        out = self.output_type
        ins = self.connection_input_types()
        if len(ins) == 1:
            return "%s → %s" % (ins[0], out)
        if ins:
            return "%s → %s" % (" + ".join(ins), out)
        return out

    def search_haystack(self, node_name: str = "") -> str:
        """Lowercase text used for palette / quick-add filtering."""
        parts = [
            node_name or self.node,
            self.node,
            self.name,
            self.doc,
            self.output_type,
            self.type_signature(),
        ]
        parts.extend(self.connection_input_types())
        return " ".join(p for p in parts if p).lower()

    def matches_filter(self, filter_text: str, node_name: str = "") -> bool:
        """True when filter tokens match this variant.

        A single token may appear anywhere in the haystack.  Two or more
        type tokens are interpreted as ``input → output`` in the order typed
        (e.g. ``float vector3`` matches float-to-vector3 converts only).
        """
        if not filter_text:
            return True
        haystack = self.search_haystack(node_name)
        tokens = filter_text.lower().split()
        ins = set(self.connection_input_types())
        outs = {self.output_type}
        port_types = ins | outs
        type_tokens = [t for t in tokens if t in port_types]
        other_tokens = [t for t in tokens if t not in port_types]
        if len(type_tokens) >= 2:
            t_in, t_out = type_tokens[0], type_tokens[1]
            if not (t_in in ins and t_out in outs):
                return False
            return all(t in haystack for t in other_tokens)
        return all(token in haystack for token in tokens)

    def palette_tooltip(self) -> str:
        """Multi-line tooltip for palette and quick-add entries."""
        lines = [self.doc or self.node]
        ins = self.connection_input_types()
        if len(ins) == 1:
            lines.append("input: %s" % ins[0])
        elif ins:
            lines.append("inputs: %s" % ", ".join(ins))
        lines.append("output: %s" % self.output_type)
        lines.append("library: %s" % self.library)
        return "\n".join(lines)

    def find_input(self, name: str) -> Optional[InputDef]:
        for i in self.inputs:
            if i.name == name:
                return i
        return None

    def find_output(self, name: str) -> Optional[OutputDef]:
        for o in self.outputs:
            if o.name == name:
                return o
        return None


class NodeDefLibrary:
    """All node definitions available to the editor, indexed for lookup."""

    def __init__(self):
        self.nodedefs: Dict[str, NodeDef] = {}        # by nodedef name
        self.by_node: Dict[str, List[NodeDef]] = {}   # by node category
        self.source_root: str = ""

    # ------------------------------------------------------------- loading

    @classmethod
    def load(cls, library_root: Optional[str] = None) -> "NodeDefLibrary":
        """Load from an explicit root, the hosting VRED install, or snapshot."""
        lib = cls()
        root = library_root or find_vred_library_root() or snapshot_root()
        if root is None or not os.path.isdir(root):
            raise FileNotFoundError(
                "No MaterialX library folder found. Inside VRED, "
                "VRED_ROOT must reference an install containing "
                "runtimeData/MaterialX/libraries.")
        lib.source_root = root
        for path in _collect_def_files(root):
            lib._parse_file(path)
        lib._resolve_inheritance()
        return lib

    def _parse_file(self, path: str):
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            return
        root = tree.getroot()
        if root.tag != "materialx":
            return
        library = _library_name(path, self.source_root)
        for elem in root.iter("nodedef"):
            nd = _parse_nodedef(elem, library, path)
            if nd is None:
                continue
            self.nodedefs[nd.name] = nd
            self.by_node.setdefault(nd.node, []).append(nd)

    def _resolve_inheritance(self):
        """Merge inherited inputs (e.g. standard_surface 1.0.1 -> 1.0.0)."""
        for nd in self.nodedefs.values():
            if not nd.inherit:
                continue
            base = self.nodedefs.get(nd.inherit)
            if base is None:
                continue
            own = {i.name for i in nd.inputs}
            merged = list(nd.inputs)
            for binput in base.inputs:
                if binput.name not in own:
                    merged.append(binput)
            nd.inputs = merged
            if not nd.outputs:
                nd.outputs = list(base.outputs)

    # -------------------------------------------------------------- lookup

    def get(self, nodedef_name: str) -> Optional[NodeDef]:
        return self.nodedefs.get(nodedef_name)

    def variants(self, node: str) -> List[NodeDef]:
        """All type signatures for a node category, default version only."""
        return [nd for nd in self.by_node.get(node, [])
                if nd.is_default_version]

    def find_variant(self, node: str, output_type: str) -> Optional[NodeDef]:
        for nd in self.variants(node):
            if nd.output_type == output_type:
                return nd
        return None

    def node_names(self) -> List[str]:
        return sorted(self.by_node.keys())

    def groups(self) -> Dict[str, List[str]]:
        """Node categories grouped by their MaterialX nodegroup."""
        out: Dict[str, List[str]] = {}
        for node, defs in self.by_node.items():
            group = ""
            for nd in defs:
                if nd.nodegroup:
                    group = nd.nodegroup
                    break
            out.setdefault(group or "other", []).append(node)
        for names in out.values():
            names.sort()
        return out

    def has_node(self, node: str) -> bool:
        return node in self.by_node


# ------------------------------------------------------------------ parsing

def _parse_nodedef(elem, library: str, path: str) -> Optional[NodeDef]:
    name = elem.get("name", "")
    node = elem.get("node", "")
    if not name or not node:
        return None
    nd = NodeDef(
        name=name,
        node=node,
        nodegroup=elem.get("nodegroup", ""),
        doc=elem.get("doc", ""),
        version=elem.get("version", ""),
        inherit=elem.get("inherit", ""),
        library=library,
        source_file=path,
    )
    # A nodedef without a version attribute is the (only) default version.
    if nd.version:
        nd.is_default_version = elem.get("isdefaultversion", "") == "true"
    for child in elem:
        if child.tag == "input":
            nd.inputs.append(_parse_input(child))
        elif child.tag == "output":
            nd.outputs.append(OutputDef(
                name=child.get("name", "out"),
                type=child.get("type", "none"),
            ))
    return nd


def _parse_input(elem) -> InputDef:
    type_name = elem.get("type", "none")
    enum_text = elem.get("enum", "")
    return InputDef(
        name=elem.get("name", ""),
        type=type_name,
        value=mtlx_types.parse_value(type_name, elem.get("value")),
        uiname=elem.get("uiname", ""),
        uifolder=elem.get("uifolder", ""),
        uimin=mtlx_types.parse_value(type_name, elem.get("uimin")),
        uimax=mtlx_types.parse_value(type_name, elem.get("uimax")),
        uisoftmin=mtlx_types.parse_value(type_name, elem.get("uisoftmin")),
        uisoftmax=mtlx_types.parse_value(type_name, elem.get("uisoftmax")),
        enum_values=tuple(v.strip() for v in enum_text.split(",") if v.strip())
        if enum_text else (),
        uniform=elem.get("uniform", "") == "true",
        advanced=elem.get("uiadvanced", "") == "true",
        defaultgeomprop=elem.get("defaultgeomprop", ""),
        doc=elem.get("doc", ""),
    )


def _library_name(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    return rel.replace("\\", "/").split("/")[0]


def _collect_def_files(root: str) -> List[str]:
    files: List[str] = []
    for pattern in _DEF_FILE_PATTERNS:
        for path in sorted(glob.glob(os.path.join(root, pattern))):
            base = os.path.basename(path)
            # Skip generator-specific duplicates and impl mapping files.
            if base.endswith("_impl.mtlx"):
                continue
            files.append(path)
    return files


# --------------------------------------------------------------- discovery

_MATERIALX_LIBRARIES = ("runtimeData", "MaterialX", "libraries")


def vred_install_root() -> Optional[str]:
    """VRED install root from the ``VRED_ROOT`` environment variable."""
    root = os.environ.get("VRED_ROOT", "").strip()
    if not root:
        return None
    normalized = os.path.normpath(root)
    return normalized if os.path.isdir(normalized) else None


def find_vred_library_root() -> Optional[str]:
    """MaterialX nodedef libraries for the VRED session hosting this plugin."""
    install = vred_install_root()
    if install is None:
        return None
    candidate = os.path.join(install, *_MATERIALX_LIBRARIES)
    return candidate if os.path.isdir(candidate) else None


def snapshot_root() -> Optional[str]:
    """The nodedef snapshot bundled with the plugin."""
    from .. import plugin_root
    root = os.path.join(plugin_root(), "resources", "libraries")
    return root if os.path.isdir(root) else None
