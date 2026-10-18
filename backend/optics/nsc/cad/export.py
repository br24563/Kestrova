"""
CAD file export module.

Supports:
- STL (ASCII and binary)
- OBJ (Wavefront)
- PLY (Polygon File Format)

STEP and IGES are boundary-representation formats; writing valid files
needs a CAD kernel, so those exporters raise NotImplementedError.
"""

from typing import Union, Optional
from pathlib import Path
import struct
import numpy as np
from .mesh import Mesh, Triangle, Vertex


def export_stl(mesh: Mesh, filepath: Union[str, Path], binary: bool = True):
    """
    Export mesh to STL file.

    Args:
        mesh: Mesh to export
        filepath: Output file path
        binary: Use binary format (smaller files)
    """
    filepath = Path(filepath)

    if binary:
        _export_stl_binary(mesh, filepath)
    else:
        _export_stl_ascii(mesh, filepath)


def _export_stl_binary(mesh: Mesh, filepath: Path):
    """Export to binary STL."""
    with open(filepath, 'wb') as f:
        # Header (80 bytes)
        f.write(b'\x00' * 80)

        # Number of triangles
        f.write(struct.pack('<I', mesh.num_triangles))

        # Write each triangle
        for tri in mesh.triangles:
            # Normal
            f.write(struct.pack('<3f', tri.normal.x, tri.normal.y, tri.normal.z))

            # Vertices
            f.write(struct.pack('<3f', tri.v0.x, tri.v0.y, tri.v0.z))
            f.write(struct.pack('<3f', tri.v1.x, tri.v1.y, tri.v1.z))
            f.write(struct.pack('<3f', tri.v2.x, tri.v2.y, tri.v2.z))

            # Attribute byte count
            f.write(struct.pack('<H', 0))


def _export_stl_ascii(mesh: Mesh, filepath: Path):
    """Export to ASCII STL."""
    with open(filepath, 'w') as f:
        f.write(f'solid {mesh.name}\n')

        for tri in mesh.triangles:
            f.write(f'  facet normal {tri.normal.x} {tri.normal.y} {tri.normal.z}\n')
            f.write('    outer loop\n')
            f.write(f'      vertex {tri.v0.x} {tri.v0.y} {tri.v0.z}\n')
            f.write(f'      vertex {tri.v1.x} {tri.v1.y} {tri.v1.z}\n')
            f.write(f'      vertex {tri.v2.x} {tri.v2.y} {tri.v2.z}\n')
            f.write('    endloop\n')
            f.write('  endfacet\n')

        f.write(f'endsolid {mesh.name}\n')


def _indexed(mesh: Mesh):
    """Shared vertex list and 0-based triangle indices (vertices merged by
    exact coordinates)."""
    index, verts, faces = {}, [], []
    for tri in mesh.triangles:
        f = []
        for v in (tri.v0, tri.v1, tri.v2):
            key = (v.x, v.y, v.z)
            if key not in index:
                index[key] = len(verts)
                verts.append(key)
            f.append(index[key])
        faces.append(f)
    return verts, faces


def export_obj(mesh: Mesh, filepath: Union[str, Path]):
    """Export mesh to Wavefront OBJ file."""
    filepath = Path(filepath)
    verts, faces = _indexed(mesh)
    with open(filepath, 'w') as f:
        f.write(f'# {mesh.name}\n')
        for x, y, z in verts:
            f.write(f'v {x} {y} {z}\n')
        for a, b, c in faces:
            f.write(f'f {a + 1} {b + 1} {c + 1}\n')


def export_step(mesh: Mesh, filepath: Union[str, Path]):
    """Not supported: a valid STEP file needs B-rep topology from a CAD kernel."""
    raise NotImplementedError("STEP export is not implemented; export STL, OBJ or PLY")


def export_iges(mesh: Mesh, filepath: Union[str, Path]):
    """Not supported: a valid IGES file needs B-rep or NURBS entities."""
    raise NotImplementedError("IGES export is not implemented; export STL, OBJ or PLY")


def export_ply(mesh: Mesh, filepath: Union[str, Path], binary: bool = False):
    """Export mesh to PLY (Polygon File Format)."""
    filepath = Path(filepath)
    verts, faces = _indexed(mesh)
    header = ('ply\n'
              f'format {"binary_little_endian" if binary else "ascii"} 1.0\n'
              f'comment {mesh.name}\n'
              f'element vertex {len(verts)}\n'
              'property float x\nproperty float y\nproperty float z\n'
              f'element face {len(faces)}\n'
              'property list uchar int vertex_indices\n'
              'end_header\n')
    with open(filepath, 'wb') as f:
        f.write(header.encode('ascii'))
        if binary:
            for v in verts:
                f.write(struct.pack('<3f', *v))
            for t in faces:
                f.write(struct.pack('<B3i', 3, *t))
        else:
            for v in verts:
                f.write(f'{v[0]} {v[1]} {v[2]}\n'.encode('ascii'))
            for t in faces:
                f.write(f'3 {t[0]} {t[1]} {t[2]}\n'.encode('ascii'))


def export_mesh(mesh: Mesh, filepath: Union[str, Path], format: Optional[str] = None):
    """
    Export mesh to file, auto-detecting format.

    Args:
        mesh: Mesh to export
        filepath: Output file path
        format: Force specific format (stl, obj, step, iges, ply)
    """
    filepath = Path(filepath)

    if format is None:
        format = filepath.suffix.lower().lstrip('.')

    if format == 'stl':
        export_stl(mesh, filepath)
    elif format == 'obj':
        export_obj(mesh, filepath)
    elif format in ('step', 'stp'):
        export_step(mesh, filepath)
    elif format in ('iges', 'igs'):
        export_iges(mesh, filepath)
    elif format == 'ply':
        export_ply(mesh, filepath)
    else:
        raise ValueError(f"Unsupported export format: {format}")
