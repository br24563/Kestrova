"""
STEP (ISO 10303) import: not supported.

STEP stores boundary-representation solids; turning them into triangles
needs a CAD kernel (for example OpenCascade), which this project does not
include. Convert STEP files to STL or OBJ first.
"""

from typing import Union
from pathlib import Path

from .mesh import Mesh


def import_step(filepath: Union[str, Path]) -> Mesh:
    """Refuse STEP import with a clear message (after checking the file)."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"STEP file not found: {filepath}")
    raise NotImplementedError(
        "STEP import needs a CAD kernel to tessellate B-rep solids; "
        "convert the file to STL or OBJ"
    )
