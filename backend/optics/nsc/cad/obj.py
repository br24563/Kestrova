"""
Wavefront OBJ file importer.

Supports vertices, normals, faces, and groups.
"""

from typing import Union
from pathlib import Path
from .mesh import Mesh, Triangle, Vertex


def import_obj(filepath: Union[str, Path]) -> Mesh:
    """
    Import a Wavefront OBJ file.
    
    Args:
        filepath: Path to OBJ file
        
    Returns:
        Mesh object
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"OBJ file not found: {filepath}")
    
    mesh = Mesh(name=filepath.stem)
    vertices = []
    normals = []
    
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            
            if not line or line.startswith('#'):
                continue
            
            parts = line.split()
            if not parts:
                continue
            
            if parts[0] == 'v':
                # Vertex
                if len(parts) >= 4:
                    v = Vertex(
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3])
                    )
                    vertices.append(v)
            
            elif parts[0] == 'vn':
                # Vertex normal
                if len(parts) >= 4:
                    normals.append((
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3])
                    ))
            
            elif parts[0] == 'f':
                # Face (triangle or polygon)
                face_vertices = []
                for part in parts[1:]:
                    # Parse vertex/texture/normal indices
                    indices = part.split('/')
                    vertex_idx = int(indices[0]) - 1  # OBJ is 1-indexed
                    if 0 <= vertex_idx < len(vertices):
                        face_vertices.append(vertices[vertex_idx])
                
                # Triangulate polygon (fan triangulation)
                if len(face_vertices) >= 3:
                    for i in range(1, len(face_vertices) - 1):
                        tri = Triangle(
                            v0=face_vertices[0],
                            v1=face_vertices[i],
                            v2=face_vertices[i + 1]
                        )
                        mesh.add_triangle(tri)
    
    return mesh
