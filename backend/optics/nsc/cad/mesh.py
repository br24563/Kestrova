"""
Mesh representation for CAD geometry.

Provides triangle mesh structure for ray tracing imported CAD files.
"""

from typing import Optional
from dataclasses import dataclass, field
import numpy as np
from ..system import Vector3, Ray, HitPoint


@dataclass
class Vertex:
    """3D vertex."""
    x: float
    y: float
    z: float
    
    def to_vector(self) -> Vector3:
        return Vector3(self.x, self.y, self.z)
    
    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])


@dataclass
class Triangle:
    """Triangle face for mesh."""
    v0: Vertex
    v1: Vertex
    v2: Vertex
    normal: Vector3 = None
    
    def __post_init__(self):
        if self.normal is None:
            self.normal = self._calculate_normal()
    
    def _calculate_normal(self) -> Vector3:
        """Calculate face normal."""
        edge1 = Vector3(
            self.v1.x - self.v0.x,
            self.v1.y - self.v0.y,
            self.v1.z - self.v0.z
        )
        edge2 = Vector3(
            self.v2.x - self.v0.x,
            self.v2.y - self.v0.y,
            self.v2.z - self.v0.z
        )
        
        # Cross product
        normal = Vector3(
            edge1.y * edge2.z - edge1.z * edge2.y,
            edge1.z * edge2.x - edge1.x * edge2.z,
            edge1.x * edge2.y - edge1.y * edge2.x
        )
        
        return normal.normalized()
    
    def intersect(self, ray: Ray) -> Optional[tuple[float, Vector3]]:
        """
        Ray-triangle intersection using Möller-Trumbore algorithm.
        
        Returns:
            (t, normal) or None
        """
        # Edge vectors
        edge1 = np.array([
            self.v1.x - self.v0.x,
            self.v1.y - self.v0.y,
            self.v1.z - self.v0.z
        ])
        edge2 = np.array([
            self.v2.x - self.v0.x,
            self.v2.y - self.v0.y,
            self.v2.z - self.v0.z
        ])
        
        # Ray direction
        ray_dir = np.array([ray.direction.x, ray.direction.y, ray.direction.z])
        ray_origin = np.array([ray.origin.x, ray.origin.y, ray.origin.z])
        v0 = np.array([self.v0.x, self.v0.y, self.v0.z])
        
        # Begin calculating determinant
        h = np.cross(ray_dir, edge2)
        a = np.dot(edge1, h)
        
        # Parallel ray
        if abs(a) < 1e-10:
            return None
        
        f = 1.0 / a
        s = ray_origin - v0
        u = f * np.dot(s, h)
        
        if u < 0.0 or u > 1.0:
            return None
        
        q = np.cross(s, edge1)
        v = f * np.dot(ray_dir, q)
        
        if v < 0.0 or u + v > 1.0:
            return None
        
        # Calculate t
        t = f * np.dot(edge2, q)
        
        if t > 1e-10:
            return (t, self.normal)
        
        return None


@dataclass
class Mesh:
    """Triangle mesh for CAD geometry."""
    name: str = "CAD_Object"
    triangles: list[Triangle] = field(default_factory=list)
    vertices: list[Vertex] = field(default_factory=list)
    
    # Bounding box
    bbox_min: Vector3 = None
    bbox_max: Vector3 = None
    
    def add_triangle(self, tri: Triangle):
        """Add triangle to mesh."""
        self.triangles.append(tri)
        self._update_bbox(tri)
    
    def add_vertex(self, v: Vertex):
        """Add vertex to mesh."""
        self.vertices.append(v)
    
    def _update_bbox(self, tri: Triangle):
        """Update bounding box."""
        for v in [tri.v0, tri.v1, tri.v2]:
            if self.bbox_min is None:
                self.bbox_min = Vector3(v.x, v.y, v.z)
                self.bbox_max = Vector3(v.x, v.y, v.z)
            else:
                self.bbox_min = Vector3(
                    min(self.bbox_min.x, v.x),
                    min(self.bbox_min.y, v.y),
                    min(self.bbox_min.z, v.z)
                )
                self.bbox_max = Vector3(
                    max(self.bbox_max.x, v.x),
                    max(self.bbox_max.y, v.y),
                    max(self.bbox_max.z, v.z)
                )
    
    def intersect(self, ray: Ray) -> Optional[HitPoint]:
        """Find nearest intersection with mesh."""
        # Quick bbox check
        if self.bbox_min and self.bbox_max:
            if not self._bbox_intersect(ray):
                return None
        
        nearest_t = float('inf')
        nearest_normal = None
        
        for tri in self.triangles:
            result = tri.intersect(ray)
            if result and result[0] < nearest_t:
                nearest_t = result[0]
                nearest_normal = result[1]
        
        if nearest_t == float('inf'):
            return None
        
        # Calculate hit point
        hit_point = Vector3(
            ray.origin.x + ray.direction.x * nearest_t,
            ray.origin.y + ray.direction.y * nearest_t,
            ray.origin.z + ray.direction.z * nearest_t
        )
        
        return HitPoint(
            ray=ray,
            object_id=0,  # Will be set by system
            point=hit_point,
            normal=nearest_normal,
            distance=nearest_t,
            inside=False
        )
    
    def _bbox_intersect(self, ray: Ray) -> bool:
        """Quick bounding box intersection test."""
        # Calculate intersection with each slab
        t_min = -float('inf')
        t_max = float('inf')
        
        for axis in ['x', 'y', 'z']:
            origin = getattr(ray.origin, axis)
            direction = getattr(ray.direction, axis)
            bbox_min = getattr(self.bbox_min, axis)
            bbox_max = getattr(self.bbox_max, axis)
            
            if abs(direction) < 1e-15:
                # Parallel to slab
                if origin < bbox_min or origin > bbox_max:
                    return False
            else:
                t1 = (bbox_min - origin) / direction
                t2 = (bbox_max - origin) / direction
                
                if t1 > t2:
                    t1, t2 = t2, t1
                
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                
                if t_min > t_max:
                    return False
        
        return t_max > 1e-10
    
    @property
    def num_triangles(self) -> int:
        return len(self.triangles)
    
    @property
    def num_vertices(self) -> int:
        return len(self.vertices)
