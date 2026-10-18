"""
Aspheric surfaces for the non-sequential tracer.

The sag functions are the same as the sequential engine's
(:mod:`optics.raytrace`): conic plus even (r^4, r^6, ...) and odd
(r, r^3, ...) polynomial terms, and Forbes Qbfs/Qcon polynomials. The
surface vertex is at ``position``, its axis along +z; normals point toward
-z (toward light arriving from -z). Lengths are in the caller's units.
"""

from typing import Optional

import numpy as np

from .system import Object3D, Vector3, Ray, HitPoint
from ..raytrace import Conicoid, RadialNumeric, q_aspheric_sag_function, curvature_from_radius


class AsphericSurface(Object3D):
    """Even aspheric surface."""

    def __init__(self, name: str = "Asphere", position: Vector3 = None, radius: float = 50.0,
                 conic: float = 0.0, aspheric_coeffs: list = None,
                 aperture_radius: float = 25.0, material: str = None):
        super().__init__(name=name, object_type="aspheric",
                         position=position or Vector3(), material=material)
        self.radius = radius
        self.conic = conic
        self.aspheric_coeffs = aspheric_coeffs or []
        self.aperture_radius = aperture_radius

    def _shape(self):
        return Conicoid(curvature_from_radius(self.radius), self.conic, self.aspheric_coeffs)

    def sag(self, r: float) -> float:
        """Sag at radial distance r (NaN where the conic is undefined)."""
        return float(self._shape().sag(np.array([r]), np.array([0.0]))[0])

    def normal_at(self, x: float, y: Optional[float] = None) -> Vector3:
        """
        Unit normal at (x, y) on the surface, pointing toward -z. Called with
        a single argument it is taken as a radial distance along x.
        """
        if y is None:
            y = 0.0
        gx, gy = self._shape().grad(np.array([x]), np.array([y]))
        return Vector3(float(gx[0]), float(gy[0]), -1.0).normalized()

    def intersect(self, ray: Ray) -> Optional[HitPoint]:
        """Intersection by Newton iteration from the vertex plane."""
        o = ray.origin - self.position
        d = ray.direction
        if abs(d.z) < 1e-15:
            return None
        shape = self._shape()
        t = -o.z / d.z
        for _ in range(60):
            x, y, z = o.x + d.x * t, o.y + d.y * t, o.z + d.z * t
            s = float(shape.sag(np.array([x]), np.array([y]))[0])
            if not np.isfinite(s):
                return None
            gx, gy = shape.grad(np.array([x]), np.array([y]))
            f = z - s
            df = d.z - float(gx[0]) * d.x - float(gy[0]) * d.y
            if abs(df) < 1e-15:
                return None
            step = f / df
            t -= step
            if abs(step) < 1e-12:
                break
        else:
            return None
        if t < 1e-10:
            return None
        x, y = o.x + d.x * t, o.y + d.y * t
        if np.hypot(x, y) > self.aperture_radius:
            return None
        n = self.normal_at(x, y)
        inside = d.dot(n) > 0
        return HitPoint(ray=ray, object_id=self.object_id, point=ray.point_at(t),
                        normal=n, distance=t, inside=inside)


class OddAsphericSurface(AsphericSurface):
    """Even asphere plus odd terms B1 r + B3 r^3 + B5 r^5 + ..."""

    def __init__(self, name: str = "OddAsphere", position: Vector3 = None, radius: float = 50.0,
                 conic: float = 0.0, aspheric_coeffs: list = None, odd_coeffs: list = None,
                 aperture_radius: float = 25.0, material: str = None):
        super().__init__(name=name, position=position, radius=radius, conic=conic,
                         aspheric_coeffs=aspheric_coeffs, aperture_radius=aperture_radius,
                         material=material)
        self.odd_coeffs = odd_coeffs or []

    def _shape(self):
        return Conicoid(curvature_from_radius(self.radius), self.conic,
                        self.aspheric_coeffs, self.odd_coeffs)


class QTypeSurface(AsphericSurface):
    """Forbes Qbfs (best-fit sphere) or Qcon (conic) asphere."""

    def __init__(self, name: str = "QAsphere", position: Vector3 = None, radius: float = 50.0,
                 conic: float = 0.0, q_type: str = "Qbfs", coefficients: list = None,
                 norm_radius: float = 25.0, aperture_radius: float = 25.0, material: str = None):
        super().__init__(name=name, position=position, radius=radius, conic=conic,
                         aperture_radius=aperture_radius, material=material)
        self.q_type = q_type
        self.coefficients = coefficients or []
        self.norm_radius = norm_radius

    def _shape(self):
        c = curvature_from_radius(self.radius)
        k = self.conic if self.q_type.lower() == "qcon" else 0.0
        f = q_aspheric_sag_function(c, k, self.coefficients, self.norm_radius, self.q_type)
        return RadialNumeric(f, c, k, scale=self.norm_radius)
