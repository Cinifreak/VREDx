# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""MaterialX type system helpers.

MaterialX stores every value as a string (e.g. ``"0.8, 0.2, 0.1"`` for a
color3).  This module converts between those strings and plain Python
values, and defines which port types may be connected together.

No Qt or VRED imports - fully unit-testable.
"""

# Types whose values are a fixed-length tuple of floats.
TUPLE_SIZES = {
    "color3": 3,
    "color4": 4,
    "vector2": 2,
    "vector3": 3,
    "vector4": 4,
}

MATRIX_SIZES = {
    "matrix33": 9,
    "matrix44": 16,
}

# All scalar/value types found in the 1.39 standard libraries.
SCALAR_TYPES = ("float", "integer", "boolean", "string", "filename", "geomname")

# Shader-semantic types: carried by connections only, never literal values.
SHADER_TYPES = (
    "surfaceshader",
    "displacementshader",
    "volumeshader",
    "lightshader",
    "material",
    "BSDF",
    "EDF",
    "VDF",
)


def is_shader_type(type_name):
    return type_name in SHADER_TYPES


def parse_value(type_name, text):
    """Parse a raw MaterialX value string into a Python value.

    Returns None for empty strings on non-string types.
    Unknown types are returned as the raw string.
    """
    if text is None:
        return None
    text = text.strip()

    if type_name in ("string", "filename", "geomname"):
        return text
    if text == "":
        return None
    if type_name == "float":
        return float(text)
    if type_name == "integer":
        return int(float(text))
    if type_name == "boolean":
        return text.lower() in ("true", "1")
    if type_name in TUPLE_SIZES or type_name in MATRIX_SIZES:
        parts = [p for p in text.replace(",", " ").split() if p]
        return tuple(float(p) for p in parts)
    return text


def format_value(type_name, value):
    """Format a Python value as a MaterialX value string."""
    if value is None:
        return ""
    if type_name in ("string", "filename", "geomname"):
        return str(value)
    if type_name == "float":
        return _fmt_float(value)
    if type_name == "integer":
        return str(int(value))
    if type_name == "boolean":
        return "true" if value else "false"
    if type_name in TUPLE_SIZES or type_name in MATRIX_SIZES:
        if isinstance(value, str):
            return value
        return ", ".join(_fmt_float(v) for v in value)
    return str(value)


def _fmt_float(value):
    # Stable, compact float formatting so writer output is deterministic.
    text = repr(float(value))
    if text.endswith(".0"):
        text = text[:-1]  # "1.0" -> "1."  -> keep "1.0" style below
        text += "0"
    return text


def types_compatible(src_type, dst_type):
    """Whether an output of src_type may connect to an input of dst_type.

    MaterialX requires exact type matches; the only tolerated mismatch in
    practice is color3<->vector3 and color4<->vector4, which the MaterialX
    spec allows implementations to auto-convert.  VRED accepts these, and
    channel-compatible conversions keep authoring fluid, so we allow them
    but the validator reports them as warnings.
    """
    if src_type == dst_type:
        return True
    return (src_type, dst_type) in _SOFT_PAIRS


_SOFT_PAIRS = {
    ("color3", "vector3"),
    ("vector3", "color3"),
    ("color4", "vector4"),
    ("vector4", "color4"),
    ("float", "color3"),
    ("float", "vector3"),
}


def is_soft_conversion(src_type, dst_type):
    """True when a connection relies on implicit conversion."""
    return src_type != dst_type and (src_type, dst_type) in _SOFT_PAIRS


def default_value(type_name):
    """A sensible zero value for a type (used for opaque/unknown inputs)."""
    if type_name == "float":
        return 0.0
    if type_name == "integer":
        return 0
    if type_name == "boolean":
        return False
    if type_name in TUPLE_SIZES:
        return tuple(0.0 for _ in range(TUPLE_SIZES[type_name]))
    if type_name in MATRIX_SIZES:
        return tuple(0.0 for _ in range(MATRIX_SIZES[type_name]))
    if type_name in ("string", "filename", "geomname"):
        return ""
    return None
