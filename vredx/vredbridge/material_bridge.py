# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Bridge between the VredX editor and VRED's MaterialX runtime.

    Graph --mtlx_writer--> <user docs>/Autodesk/VredX/<name>.mtlx
          --vrMaterialService.createMaterial(name, MaterialType.MaterialX)
          --vrdMaterialXMaterial.loadMaterial(path, 0)
"""

import os
import re

from ..core import mtlx_writer
from ..core.graph import Graph
from . import vred_api

PREVIEW_RESOLUTION = 256


class BridgeError(RuntimeError):
    """Raised when VRED material operations fail."""


class MaterialBridge:
    """Stateful helper bound to the current VRED session."""

    def __init__(self, output_dir=None):
        self.output_dir = output_dir or vred_api.user_documents_dir()
        # Most recently applied material; the preview panel shows this one.
        self.last_material = None
        # VRED material name last sent from the editor (survives renames in
        # the graph until the next successful apply).
        self._linked_vred_name = None

    # ------------------------------------------------------------- writing

    def write_mtlx(self, graph: Graph, path=None) -> str:
        """Serialize the graph to disk; returns the file path."""
        if path is None:
            path = os.path.join(self.output_dir,
                                _safe_filename(graph.name) + ".mtlx")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mtlx_writer.save_document(graph, path)
        return path

    # ------------------------------------------------------------ applying

    def apply_graph(self, graph: Graph, assign_to_selection=False,
                    pulse=None):
        """Create/refresh a VRED MaterialX material from the graph.

        Always reloads the generated document via ``loadMaterial``.

        ``pulse(message)`` is an optional callback invoked between slow
        stages so the UI can update a progress dialog.

        Returns ``(material, mtlx_path)``.
        """
        vred_api.require_vred()
        service = vred_api.vrMaterialService
        if service is None:
            raise BridgeError("vrMaterialService is not available.")

        path = self.write_mtlx(graph)

        if pulse:
            pulse("Compiling material in VRED…")

        material = self._resolve_material(service, graph.name, path)
        if material is not None:
            if not material.loadMaterial(path, 0):
                raise BridgeError(
                    "VRED failed to reload the generated document:\n%s\n"
                    "Check the Terminal for MaterialX compile errors." % path)
        else:
            material = _create_material(service, graph.name, path)
        if material is None or not material.isValid():
            raise BridgeError("Could not create MaterialX material '%s'"
                              % graph.name)

        if assign_to_selection:
            self._assign_to_selection(material)

        self.last_material = material
        try:
            self._linked_vred_name = material.getName()
        except AttributeError:
            self._linked_vred_name = graph.name
        return material, path

    def _resolve_material(self, service, graph_name, path):
        """Return an existing MaterialX material to update, or None."""
        linked = self._linked_vred_name
        renamed = linked and not _names_match(graph_name, linked)

        if not renamed:
            if _is_valid_materialx(self.last_material):
                try:
                    if _names_match(self.last_material.getName(), graph_name):
                        return self.last_material
                except AttributeError:
                    pass

            norm_path = _norm_path(path)
            for material in service.getAllMaterials():
                if not _is_valid_materialx(material):
                    continue
                if _norm_path(_material_source_path(material)) == norm_path:
                    return material

        found = _find_material_by_name(service, graph_name)
        if found is not None:
            return found
        return None

    def assign_to_selection(self, material):
        """Apply *material* to the current scenegraph selection.

        Returns the number of nodes updated (0 if nothing selected).
        """
        vred_api.require_vred()
        return self._assign_to_selection(material)

    def _assign_to_selection(self, material):
        vred_api.require_vred()
        try:
            import builtins
            scenegraph = getattr(builtins, "vrScenegraphService", None)
            if scenegraph is None:
                import vrScenegraphService as scenegraph  # type: ignore
            nodes = scenegraph.getSelectedNodes()
        except (AttributeError, ImportError, RuntimeError) as exc:
            raise BridgeError(
                "Could not read the scene selection: %s" % exc) from exc
        if not nodes:
            return 0
        try:
            vred_api.vrMaterialService.applyMaterialToNodes(material, nodes)
        except (AttributeError, RuntimeError) as exc:
            raise BridgeError(
                "Could not assign the material to the selection: %s"
                % exc) from exc
        return len(nodes)

    # ----------------------------------------------------- property access

    def list_properties(self, material):
        """Names of all MaterialX attributes exposed by a loaded material."""
        vred_api.require_vred()
        from PySide6 import QtCore
        obj = QtCore.QObject()
        _as_materialx(material).getProperties().update(obj)
        return [bytes(name).decode("utf-8")
                for name in obj.dynamicPropertyNames()]

    def set_property(self, material, parameter_id, value, type_name=None):
        """Fast single-attribute update without reloading the document."""
        vred_api.require_vred()
        mtlx = _as_materialx(material)
        if not hasattr(mtlx, "setActiveMaterialProperty"):
            raise BridgeError("setActiveMaterialProperty unavailable")
        mtlx.setActiveMaterialProperty(
            parameter_id, _to_qvariant(value, type_name))

    def get_property(self, material, parameter_id):
        vred_api.require_vred()
        return _as_materialx(material).getActiveMaterialProperty(parameter_id)

    # ------------------------------------------------------------ previews

    def request_preview(self, material=None):
        """Ask VRED to (re)render the swatch for a material.

        Always queues ``updatePreviews``; listen to ``previewsChanged`` and
        call :meth:`capture_preview` to pull a fresh image at
        :data:`PREVIEW_RESOLUTION`.
        """
        vred_api.require_vred()
        material = material or self.last_material
        if material is None:
            return
        self.ensure_vball_preview(material)
        vred_api.vrMaterialService.updatePreviews([material])

    def capture_preview(self, material=None):
        """Return a fresh swatch QImage at :data:`PREVIEW_RESOLUTION`."""
        vred_api.require_vred()
        material = material or self.last_material
        if material is None:
            return None
        service = vred_api.vrMaterialService
        try:
            from PySide6.QtCore import QSize
            render = getattr(service, "renderMultiPreview", None)
            if render is not None:
                image = render(
                    [material], 1,
                    QSize(PREVIEW_RESOLUTION, PREVIEW_RESOLUTION), "")
                if image is not None and not image.isNull():
                    return image
        except (AttributeError, TypeError, RuntimeError):
            pass
        try:
            image = material.getPreview()
        except AttributeError:
            return None
        return None if image is None or image.isNull() else image

    def preview_scenes(self):
        """Names of the swatch geometries VRED offers (sphere, ...)."""
        vred_api.require_vred()
        try:
            return list(vred_api.vrMaterialService.getPreviewScenes())
        except AttributeError:
            return []

    def resolve_vball_scene(self, scenes=None):
        """The v-ball preview scene name (exact match from VRED when possible)."""
        target = "v-ball"
        if scenes is None:
            try:
                scenes = self.preview_scenes()
            except RuntimeError:
                scenes = []
        for name in scenes:
            if name.lower().replace("_", "-") == target:
                return name
        return target

    def ensure_vball_preview(self, material=None):
        """Force the material swatch to use the v-ball geometry."""
        vred_api.require_vred()
        material = material or self.last_material
        if material is None:
            return
        try:
            material.setPreviewScene(self.resolve_vball_scene())
        except AttributeError:
            pass

    def set_preview_scene(self, name, material=None):
        """Select the swatch geometry, then re-render the preview."""
        vred_api.require_vred()
        material = material or self.last_material
        if material is None or not name:
            return
        try:
            material.setPreviewScene(name)
        except AttributeError:
            return
        self.request_preview(material)

    # ------------------------------------------------------ scene queries

    def scene_materialx_materials(self):
        """All MaterialX materials in the current scene."""
        vred_api.require_vred()
        result = []
        for material in vred_api.vrMaterialService.getAllMaterials():
            if _is_materialx(material):
                result.append(material)
        return result

    def material_source_path(self, material):
        """Path of the .mtlx document behind a scene material ('' if none)."""
        return _material_source_path(material)


# --------------------------------------------------------------- helpers

def _as_materialx(material):
    """Return a ``vrdMaterialXMaterial`` view (required for property API)."""
    if material is None:
        return material
    cls = vred_api.vrdMaterialXMaterial
    if cls is None:
        return material
    try:
        mtlx = cls(material)
    except Exception:
        return material
    try:
        if hasattr(mtlx, "isValid") and mtlx.isValid():
            return mtlx
    except Exception:
        pass
    return material


def _create_material(service, name, path):
    """Create a new MaterialX material and load the document."""
    existing = _find_material_by_name(service, name)
    if _is_valid_materialx(existing):
        if existing.loadMaterial(path, 0):
            return existing

    try:
        material = service.createMaterial(name, vred_api.material_x_type())
        if material is not None and material.isValid():
            if material.loadMaterial(path, 0):
                return material
    except RuntimeError:
        pass

    # Last resort when createMaterial is unavailable: loadMaterials may
    # register a new scene material (avoid when _resolve_material can link).
    try:
        loaded = service.loadMaterials([path])
    except Exception:
        loaded = []
    if loaded:
        for candidate in loaded:
            if _is_valid_materialx(candidate):
                return candidate
        return loaded[0]
    return None


def _find_material_by_name(service, name):
    """Locate a MaterialX material by scene name."""
    if not name:
        return None
    try:
        material = service.findMaterial(name)
    except Exception:
        material = None
    if _is_valid_materialx(material):
        return material
    target = name.strip().casefold()
    for candidate in service.getAllMaterials():
        if not _is_valid_materialx(candidate):
            continue
        try:
            cname = candidate.getName()
        except AttributeError:
            continue
        if cname == name or cname.strip().casefold() == target:
            return candidate
    return None


def _material_source_path(material):
    try:
        return material.getPath() or ""
    except AttributeError:
        return ""


def _norm_path(path):
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path))


def _is_materialx(material):
    if material is None:
        return False
    try:
        if vred_api.vrdMaterialXMaterial is not None:
            return material.isType(vred_api.vrdMaterialXMaterial)
        return type(material).__name__ == "vrdMaterialXMaterial"
    except Exception:
        return False


def _is_valid_materialx(material):
    try:
        return material is not None and material.isValid() and \
            _is_materialx(material)
    except Exception:
        return False


def _to_qvariant(value, type_name=None):
    """Best-effort conversion of core values to Qt-friendly ones."""
    from PySide6 import QtGui

    if isinstance(value, tuple):
        if type_name in ("color3", "color4") or (
                type_name is None and len(value) in (3, 4)):
            color = QtGui.QColor.fromRgbF(
                *[max(0.0, min(1.0, float(c))) for c in value[:3]])
            if len(value) == 4:
                color.setAlphaF(max(0.0, min(1.0, float(value[3]))))
            return color
        if len(value) == 2:
            return QtGui.QVector2D(*value)
        if len(value) == 3:
            return QtGui.QVector3D(*value)
        if len(value) == 4:
            return QtGui.QVector4D(*value)
        return list(value)
    return value


def _safe_filename(name):
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name) or "material"


# Install locations that are never safe Save targets for script plugins.
_READ_ONLY_PREFIXES = tuple(
    os.path.normcase(entry) for entry in (
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ))


def default_document_path(output_dir, graph_name):
    """User-writable .mtlx path for a material graph."""
    return os.path.join(output_dir, _safe_filename(graph_name) + ".mtlx")


def is_writable_path(path):
    """True when *path* can be created or overwritten."""
    if not path:
        return False
    absolute = os.path.normcase(os.path.abspath(path))
    for prefix in _READ_ONLY_PREFIXES:
        if absolute.startswith(prefix + os.sep):
            return False
    directory = os.path.dirname(absolute)
    if os.path.isdir(directory):
        return os.access(directory, os.W_OK)
    parent = os.path.dirname(directory)
    return bool(parent) and os.path.isdir(parent) and os.access(parent, os.W_OK)


def _names_match(left, right):
    if not left or not right:
        return False
    return left == right or left.strip().casefold() == right.strip().casefold()
