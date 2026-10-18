"""
STL file importer.

Supports both ASCII and binary STL formats.
"""

import struct
import numpy as np
from typing import Union
from pathlib import Path
from .mesh import Mesh, Triangle, Vertex


def import_stl(filepath: Union[str, Path]) -> Mesh:
    """
    Import an STL file (ASCII or binary).
    
    Args:
        filepath: Path to STL file
        
    Returns:
        Mesh object
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"STL file not found: {filepath}")
    
    # Detect format by reading first few bytes
    with open(filepath, 'rb') as f:
        header = f.read(80)
    
    # Check if ASCII
    try:
        header_str = header.decode('ascii', errors='ignore').strip()
        if header_str.startswith('solid'):
            return _import_stl_ascii(filepath)
    except:
        pass
    
    # Otherwise binary
    return _import_stl_binary(filepath)


def _import_stl_ascii(filepath: Path) -> Mesh:
    """Import ASCII STL file."""
    mesh = Mesh(name=filepath.stem)
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    current_normal = None
    current_vertices = []
    
    for line in lines:
        line = line.strip()
        
        if line.startswith('facet normal'):
            # Parse normal
            parts = line.split()
            if len(parts) >= 5:
                current_normal = Vertex(
                    float(parts[2]),
                    float(parts[3]),
                    float(parts[4])
                )
        
        elif line.startswith('vertex'):
            # Parse vertex
            parts = line.split()
            if len(parts) >= 4:
                v = Vertex(
                    float(parts[1]),
                    float(parts[2]),
                    float(parts[3])
                )
                current_vertices.append(v)
        
        elif line.startswith('endfacet'):
            # Create triangle
            if len(current_vertices) == 3:
                tri = Triangle(
                    v0=current_vertices[0],
                    v1=current_vertices[1],
                    v2=current_vertices[2]
                )
                mesh.add_triangle(tri)
            
            current_vertices = []
            current_normal = None
    
    return mesh


def _import_stl_binary(filepath: Path) -> Mesh:
    """Import binary STL file."""
    mesh = Mesh(name=filepath.stem)
    
    with open(filepath, 'rb') as f:
        # Skip header (80 bytes)
        f.read(80)
        
        # Read number of triangles
        num_triangles = struct.unpack('<I', f.read(4))[0]
        
        for _ in range(num_triangles):
            # Read normal (3 floats)
            nx, ny, nz = struct.unpack('<3f', f.read(12))
            
            # Read vertices (9 floats)
            v0x, v0y, v0z = struct.unpack('<3f', f.read(12))
            v1x, v1y, v1z = struct.unpack('<3f', f.read(12))
            v2x, v2y, v2z = struct.unpack('<3f', f.read(12))
            
            # Create triangle
            tri = Triangle(
                v0=Vertex(v0x, v0y, v0z),
                v1=Vertex(v1x, v1y, v1z),
                v2=Vertex(v2x, v2y, v2z)
            )
            mesh.add_triangle(tri)
            
            # Skip attribute byte count
            f.read(2)
    
    return mesh
