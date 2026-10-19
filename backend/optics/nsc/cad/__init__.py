"""CAD file import/export module.

Supports:
- STL (ASCII and binary) - Import/Export
- OBJ (Wavefront) - Import/Export
- PLY (Polygon File Format) - Export
- STEP, IGES - not supported (B-rep formats need a CAD kernel); convert
  to STL or OBJ
"""

from .mesh import Mesh, Triangle, Vertex
from .stl import import_stl
from .obj import import_obj
from .importer import import_cad_file, get_supported_formats
from .export import (
    export_stl,
    export_obj,
    export_step,
    export_iges,
    export_ply,
    export_mesh,
)

__all__ = [
    "Mesh",
    "Triangle",
    "Vertex",
    "import_stl",
    "import_obj",
    "import_cad_file",
    "get_supported_formats",
    "export_stl",
    "export_obj",
    "export_step",
    "export_iges",
    "export_ply",
    "export_mesh",
]
