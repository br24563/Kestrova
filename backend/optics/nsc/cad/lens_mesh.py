"""
Triangle meshes of a sequential system's elements, for STL/OBJ/PLY export.

Each ThickLens becomes a closed solid of revolution (front surface, back
surface, cylindrical edge); a curved or flat Mirror becomes its reflecting
surface only (the model has no substrate thickness). Ideal thin lenses have
no physical shape and are skipped. Coordinates are in millimetres with z
along the optical axis.
"""

import math

import numpy as np

from .mesh import Mesh, Triangle, Vertex
from ...models import OpticalSystem, ThickLens, ThinLens, Mirror


def _sag(radius: float, conic: float, r: np.ndarray) -> np.ndarray:
    if radius == 0 or abs(radius) > 1e9:
        return np.zeros_like(r)
    c = 1.0 / radius
    arg = 1.0 - (1.0 + conic) * c * c * r * r
    if np.any(arg < 0):
        raise ValueError("Aperture exceeds the extent of the conic surface")
    return c * r * r / (1.0 + np.sqrt(arg))


def _surface_grid(z0, radius, conic, semi, rings, segments):
    """Rings of vertices (ring 0 is the vertex point)."""
    r = np.linspace(0.0, semi, rings + 1)
    z = z0 + _sag(radius, conic, r)
    phi = np.linspace(0.0, 2 * math.pi, segments, endpoint=False)
    grid = [[Vertex(0.0, 0.0, float(z[0]))]]
    for k in range(1, rings + 1):
        grid.append(
            [
                Vertex(
                    float(r[k] * math.cos(p)), float(r[k] * math.sin(p)), float(z[k])
                )
                for p in phi
            ]
        )
    return grid


def _cap(mesh, grid, flip):
    def tri(a, b, c):
        mesh.add_triangle(Triangle(a, c, b) if flip else Triangle(a, b, c))

    n = len(grid[1])
    for j in range(n):
        tri(grid[0][0], grid[1][j], grid[1][(j + 1) % n])
    for k in range(1, len(grid) - 1):
        for j in range(n):
            a, b = grid[k][j], grid[k][(j + 1) % n]
            c, d = grid[k + 1][j], grid[k + 1][(j + 1) % n]
            tri(a, c, d)
            tri(a, d, b)


def _edge(mesh, ring_front, ring_back):
    n = len(ring_front)
    for j in range(n):
        a, b = ring_front[j], ring_front[(j + 1) % n]
        c, d = ring_back[j], ring_back[(j + 1) % n]
        mesh.add_triangle(Triangle(a, d, c))
        mesh.add_triangle(Triangle(a, b, d))


def system_meshes(system: OpticalSystem, rings: int = 16, segments: int = 64):
    """(list of Mesh, list of (component id, reason) for skipped components)."""
    meshes, skipped = [], []
    mm = 1000.0
    for comp in sorted(system.components, key=lambda c: c.position):
        if isinstance(comp, ThickLens):
            semi = comp.aperture_diameter / 2 * mm
            z0 = comp.position * mm
            front = _surface_grid(z0, comp.radius1 * mm, 0.0, semi, rings, segments)
            back = _surface_grid(
                z0 + comp.thickness * mm, comp.radius2 * mm, 0.0, semi, rings, segments
            )
            if back[-1][0].z <= front[-1][0].z:
                raise ValueError(f"{comp.id}: edge thickness is not positive")
            m = Mesh(name=comp.id)
            _cap(m, front, flip=True)  # outward normals toward -z
            _cap(m, back, flip=False)
            _edge(m, front[-1], back[-1])
            meshes.append(m)
        elif isinstance(comp, Mirror):
            semi = (comp.aperture_diameter or comp.width) / 2 * mm
            m = Mesh(name=comp.id)
            _cap(
                m,
                _surface_grid(
                    comp.position * mm,
                    comp.radius * mm,
                    comp.conic,
                    semi,
                    rings,
                    segments,
                ),
                flip=False,
            )
            meshes.append(m)
        elif isinstance(comp, ThinLens):
            skipped.append((comp.id, "ideal thin lens has no physical shape"))
        else:
            skipped.append((comp.id, f"no mesh generator for {comp.type}"))
    return meshes, skipped


def merge_meshes(meshes, name: str = "System") -> Mesh:
    out = Mesh(name=name)
    for m in meshes:
        for t in m.triangles:
            out.add_triangle(t)
    return out
