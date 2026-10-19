"""
IGES import: not supported.

IGES stores curves, NURBS surfaces and B-rep entities; turning them into
triangles needs a CAD kernel, which this project does not include. Convert
IGES files to STL or OBJ first.
"""

from typing import Union
from pathlib import Path

from .mesh import Mesh


def import_iges(filepath: Union[str, Path]) -> Mesh:
    """Refuse IGES import with a clear message (after checking the file)."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"IGES file not found: {filepath}")
    raise NotImplementedError(
        "IGES import needs a CAD kernel to tessellate its surfaces; "
        "convert the file to STL or OBJ"
    )
