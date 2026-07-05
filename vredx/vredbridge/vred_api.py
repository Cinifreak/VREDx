# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Guarded access to the VRED Python API.

Inside VRED the service modules (vrMaterialService, vrMaterialTypes...)
are injected into builtins at startup; importing them as modules also
works.  Outside VRED every symbol is None and INSIDE_VRED is False, so
the rest of the package imports cleanly under pytest.
"""

INSIDE_VRED = False

vrMaterialService = None
vrMaterialTypes = None
vrdMaterialXMaterial = None
vrFileIOService = None


def _resolve_vred_services():
    """Bind VRED service modules/objects once at import time."""
    global INSIDE_VRED, vrMaterialService, vrMaterialTypes
    import builtins

    service = None
    types = None

    try:
        import vrMaterialService as _service  # type: ignore
        service = _service
    except ImportError:
        service = getattr(builtins, "vrMaterialService", None)

    types = _import_material_types()

    vrMaterialService = service
    vrMaterialTypes = types
    INSIDE_VRED = service is not None


def _import_material_types():
    """vrMaterialTypes is usually in vrKernelServices, not a top-level module."""
    import builtins

    try:
        import vrMaterialTypes as types  # type: ignore
        return types
    except ImportError:
        pass

    try:
        from vrKernelServices import vrMaterialTypes as types  # type: ignore
        return types
    except ImportError:
        pass

    return getattr(builtins, "vrMaterialTypes", None)


_resolve_vred_services()

if INSIDE_VRED:
    try:
        from vrKernelServices import vrdMaterialXMaterial  # type: ignore
    except ImportError:
        try:
            import builtins
            vrdMaterialXMaterial = getattr(
                builtins, "vrdMaterialXMaterial", None)
        except Exception:
            vrdMaterialXMaterial = None
    try:
        import vrFileIOService        # type: ignore  # noqa: F401
    except ImportError:
        pass


def require_vred():
    if not INSIDE_VRED:
        raise RuntimeError(
            "This operation requires a running VRED session.")


def material_x_type():
    """The vrMaterialTypes enum value for MaterialX materials."""
    require_vred()
    global vrMaterialTypes

    types = vrMaterialTypes or _import_material_types()
    if types is not None:
        vrMaterialTypes = types
        try:
            return types.MaterialType.MaterialX
        except AttributeError:
            try:
                return types.MaterialX
            except AttributeError:
                pass

    service = vrMaterialService
    if service is not None:
        try:
            for mt in service.getSupportedMaterialTypes():
                label = str(mt)
                if label == "MaterialX" or label.endswith(".MaterialX"):
                    return mt
        except Exception:
            pass

    raise RuntimeError(
        "Could not resolve MaterialX material type in VRED "
        "(vrMaterialTypes and getSupportedMaterialTypes both failed).")


def user_documents_dir():
    """Folder for generated .mtlx files (VRED user dir or temp)."""
    import os
    import tempfile
    docs = os.path.join(os.path.expanduser("~"), "Documents",
                        "Autodesk", "VredX")
    try:
        os.makedirs(docs, exist_ok=True)
        return docs
    except OSError:
        return tempfile.gettempdir()
