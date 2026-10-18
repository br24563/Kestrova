"""
Surface scatter models for the non-sequential tracer (reflective scatter).

Each model returns ``num_rays`` scattered rays whose weights form an
unbiased Monte Carlo estimate of the scattered power:

    P_scattered = P_in * integral BSDF(beta) cos(theta_s) dOmega

Directions are drawn cosine-weighted over the reflection hemisphere
(pdf cos(theta)/pi), so each ray carries P_in * pi * BSDF / N. ``beta`` is
the distance, in the surface's direction-cosine plane, between the scatter
direction and the specular direction (the Harvey/ABg convention).
"""

import numpy as np

from .system import Ray, HitPoint, Vector3


def _frame(normal: Vector3):
    n = normal.normalized()
    ref = Vector3(1, 0, 0) if abs(n.x) < 0.9 else Vector3(0, 1, 0)
    t = Vector3(ref.y * n.z - ref.z * n.y, ref.z * n.x - ref.x * n.z,
                ref.x * n.y - ref.y * n.x).normalized()
    b = Vector3(n.y * t.z - n.z * t.y, n.z * t.x - n.x * t.z, n.x * t.y - n.y * t.x)
    return n, t, b


def _facing(normal: Vector3, ray: Ray) -> Vector3:
    """Normal on the side the ray arrives from (the reflection hemisphere)."""
    if ray.direction.dot(normal) > 0:
        return Vector3(-normal.x, -normal.y, -normal.z)
    return normal


class ScatterModel:
    """Base class: subclasses implement ``bsdf(beta)`` (1/sr)."""

    num_rays: int = 10
    rng = np.random.default_rng()

    def bsdf(self, beta: float, cos_s: float = 1.0) -> float:
        raise NotImplementedError

    def scatter(self, ray: Ray, hit: HitPoint) -> list:
        n, t, b = _frame(_facing(hit.normal, ray))
        d = ray.direction
        dn = d.dot(n)
        spec = Vector3(d.x - 2 * dn * n.x, d.y - 2 * dn * n.y, d.z - 2 * dn * n.z)
        s0 = (spec.dot(t), spec.dot(b))
        out = []
        for _ in range(self.num_rays):
            r = np.sqrt(self.rng.uniform())
            phi = self.rng.uniform(0, 2 * np.pi)
            lx, ly = r * np.cos(phi), r * np.sin(phi)
            lz = np.sqrt(max(0.0, 1 - r * r))
            beta = float(np.hypot(lx - s0[0], ly - s0[1]))
            w = np.pi * self.bsdf(beta, lz) / self.num_rays
            direction = Vector3(lx * t.x + ly * b.x + lz * n.x,
                                lx * t.y + ly * b.y + lz * n.y,
                                lx * t.z + ly * b.z + lz * n.z).normalized()
            out.append(Ray(origin=hit.point, direction=direction,
                           intensity=ray.intensity * w, wavelength=ray.wavelength,
                           order=ray.order + 1))
        return out


class NoScatter(ScatterModel):
    """No scattering."""

    def scatter(self, ray: Ray, hit: HitPoint) -> list:
        return []


class LambertianScatter(ScatterModel):
    """Lambertian: BSDF = reflectance / pi."""

    def __init__(self, num_rays: int = 10, reflectance: float = 0.1):
        self.num_rays = num_rays
        self.reflectance = reflectance

    def bsdf(self, beta: float, cos_s: float = 1.0) -> float:
        return self.reflectance / np.pi


class GaussianScatter(ScatterModel):
    """
    Gaussian lobe about the specular direction in direction-cosine space,
    BSDF = TS exp(-beta^2 / 2 s^2) / (2 pi s^2 cos theta_s); for a narrow
    lobe the total scatter is close to TS. ``sigma`` is given in degrees and
    converted to direction-cosine units as s = sin(sigma).
    """

    def __init__(self, num_rays: int = 10, sigma: float = 5.0, reflectance: float = 0.1):
        self.num_rays = num_rays
        self.s = np.sin(np.radians(sigma))
        self.reflectance = reflectance

    def bsdf(self, beta: float, cos_s: float = 1.0) -> float:
        return (self.reflectance * np.exp(-0.5 * (beta / self.s) ** 2)
                / (2 * np.pi * self.s ** 2 * max(cos_s, 1e-6)))


class ABgScatter(ScatterModel):
    """Harvey-Shack ABg: BSDF = A / (B + beta^g)."""

    def __init__(self, num_rays: int = 10, A: float = 0.01, B: float = 0.01, G: float = 2.0):
        self.num_rays = num_rays
        self.A, self.B, self.G = A, B, G

    def bsdf(self, beta: float, cos_s: float = 1.0) -> float:
        return self.A / (self.B + beta ** self.G)
