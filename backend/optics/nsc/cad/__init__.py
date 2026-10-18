"""CAD file import/export module.

Supports:
- STL (ASCII and binary) - Import/Export
- OBJ (Wavefront) - Import/Export
- PLY (Polygon File Format) - Export
- STEP - import through OpenCascade only (import_step_full parses a subset)
- IGES - not supported by import_cad_file (import_iges_full parses a subset)
"""
from .mesh import Mesh, Triangle, Vertex
from .stl import import_stl
from .obj import import_obj
from .step_full import import_step_full
from .iges_full import import_iges_full
from .importer import import_cad_file, get_supported_formats
from .export import (
    export_stl, export_obj, export_step, export_iges, export_ply,
    export_mesh
)

__all__ = [
    'Mesh',
    'Triangle',
    'Vertex',
    'import_stl',
    'import_obj',
    'import_step_full',
    'import_iges_full',
    'import_cad_file',
    'get_supported_formats',
    'export_stl',
    'export_obj',
    'export_step',
    'export_iges',
    'export_ply',
    'export_mesh',
]
