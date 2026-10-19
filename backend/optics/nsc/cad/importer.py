"""
CAD file importer - auto-detects format and imports.
"""

from typing import Union
from pathlib import Path
from .mesh import Mesh
from .stl import import_stl
from .obj import import_obj
from .step import import_step
from .iges import import_iges


def import_cad_file(filepath: Union[str, Path]) -> Mesh:
    """
    Import a CAD file, auto-detecting the format.

    Supported formats:
    - STL (ASCII and binary)
    - OBJ (Wavefront)
    STEP and IGES are recognised but refused (NotImplementedError): they
    need a CAD kernel.

    Args:
        filepath: Path to CAD file

    Returns:
        Mesh object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If format is unsupported
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"CAD file not found: {filepath}")

    # Detect format from extension
    ext = filepath.suffix.lower()

    if ext == ".stl":
        return import_stl(filepath)
    elif ext == ".obj":
        return import_obj(filepath)
    elif ext in (".step", ".stp"):
        return import_step(filepath)
    elif ext in (".iges", ".igs"):
        return import_iges(filepath)
    else:
        raise ValueError(f"Unsupported CAD format: {ext}")


def get_supported_formats() -> dict:
    """Supported CAD formats and what is implemented for each."""
    return {
        "stl": {
            "name": "STL",
            "description": "Stereolithography (ASCII and binary)",
            "extensions": [".stl"],
            "import": True,
            "export": True,
        },
        "obj": {
            "name": "OBJ",
            "description": "Wavefront OBJ",
            "extensions": [".obj"],
            "import": True,
            "export": True,
        },
        "ply": {
            "name": "PLY",
            "description": "Polygon File Format",
            "extensions": [".ply"],
            "import": False,
            "export": True,
        },
        "step": {
            "name": "STEP",
            "description": "ISO 10303",
            "extensions": [".step", ".stp"],
            "import": False,
            "export": False,
        },
        "iges": {
            "name": "IGES",
            "description": "Initial Graphics Exchange Specification",
            "extensions": [".iges", ".igs"],
            "import": False,
            "export": False,
        },
    }
