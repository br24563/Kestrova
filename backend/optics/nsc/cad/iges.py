"""
IGES file importer (5.3).

Basic implementation for IGES geometry import.
"""

from typing import Union
from pathlib import Path
from .mesh import Mesh, Triangle, Vertex


def import_iges(filepath: Union[str, Path]) -> Mesh:
    """
    Import an IGES file.

    Args:
        filepath: Path to IGES file

    Returns:
        Mesh object
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"IGES file not found: {filepath}")

    mesh = Mesh(name=filepath.stem)

    with open(filepath, "r") as f:
        lines = f.readlines()

    # Check for IGES format
    if not lines or lines[-1].strip() != "S":
        # Try to parse anyway
        pass

    # Extract directory and parameter data
    directory_lines = []
    parameter_lines = []

    for line in lines:
        if len(line) >= 73:
            section_type = line[72]
            if section_type == "D":
                directory_lines.append(line[:72])
            elif section_type == "P":
                parameter_lines.append(line[:64])

    # Parse entities (basic)
    # IGES entity types we care about:
    # 110: Line
    # 116: Point
    # 120: Surface of revolution
    # 122: Tabulated cylinder
    # 124: Transformation matrix
    # 126: Rational B-spline curve
    # 128: Rational B-spline surface
    # 144: Trimmed surface
    # 186: Manifold solid B-rep
    # 502: Vertex
    # 504: Edge
    # 508: Loop
    # 510: Face
    # 514: Shell

    raise NotImplementedError(
        "IGES geometry import is not implemented; convert to STL instead"
    )
