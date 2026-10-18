"""
Non-sequential optical system definition.

In NSC mode, rays can hit objects in any order, split at interfaces,
and scatter. Objects are 3D volumes, not just surfaces.
"""

from typing import Optional
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Vector3:
    """3D vector for positions and directions."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other):
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar):
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def magnitude(self) -> float:
        return np.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalized(self) -> 'Vector3':
        mag = self.magnitude()
        if mag < 1e-15:
            return Vector3(0, 0, 0)
        return Vector3(self.x / mag, self.y / mag, self.z / mag)

    def dot(self, other) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

    @staticmethod
    def from_array(arr: np.ndarray) -> 'Vector3':
        return Vector3(arr[0], arr[1], arr[2])


@dataclass
class Ray:
    """A ray in 3D space."""
    origin: Vector3
    direction: Vector3
    intensity: float = 1.0
    wavelength: float = 550e-9
    order: int = 0  # Reflection order
    path_length: float = 0.0

    def point_at(self, t: float) -> Vector3:
        """Get point at distance t along ray."""
        return self.origin + self.direction * t


@dataclass
class HitPoint:
    """Where a ray hits an object."""
    ray: Ray
    object_id: int
    point: Vector3
    normal: Vector3
    distance: float
    inside: bool  # Are we entering or exiting


@dataclass
class Source:
    """Ray source object."""
    name: str = "Source"
    position: Vector3 = field(default_factory=Vector3)
    direction: Vector3 = field(default_factory=lambda: Vector3(0, 0, 1))
    intensity: float = 1.0
    wavelength: float = 550e-9
    num_rays: int = 1000
    source_type: str = "point"  # point, lambertian, radial
    half_angle: float = 30.0  # For Lambertian/radial sources (degrees)

    def generate_rays(self) -> list[Ray]:
        """Generate rays from this source."""
        rays = []

        if self.source_type == "point":
            # Isotropic point source
            for i in range(self.num_rays):
                # Fibonacci sphere distribution
                phi = np.arccos(1 - 2 * (i + 0.5) / self.num_rays)
                theta = np.pi * (1 + np.sqrt(5)) * i

                dx = np.sin(phi) * np.cos(theta)
                dy = np.sin(phi) * np.sin(theta)
                dz = np.cos(phi)

                rays.append(Ray(
                    origin=self.position,
                    direction=Vector3(dx, dy, dz).normalized(),
                    intensity=self.intensity / self.num_rays,
                    wavelength=self.wavelength
                ))

        elif self.source_type == "lambertian":
            # Lambertian: radiance constant, so the ray density in direction
            # theta goes as cos(theta) sin(theta); sin^2(theta) is uniform.
            s_max = np.sin(np.radians(self.half_angle))
            for i in range(self.num_rays):
                r = s_max * np.sqrt(np.random.uniform(0.0, 1.0))
                z = np.sqrt(1 - r**2)
                phi = np.random.uniform(0, 2 * np.pi)

                # Local coordinates
                local_dir = Vector3(r * np.cos(phi), r * np.sin(phi), z).normalized()

                # Rotate to align with source direction
                world_dir = self._rotate_to_direction(local_dir)

                rays.append(Ray(
                    origin=self.position,
                    direction=world_dir,
                    intensity=self.intensity / self.num_rays,
                    wavelength=self.wavelength
                ))

        elif self.source_type == "collimated":
            # Collimated beam with slight divergence
            for i in range(self.num_rays):
                rays.append(Ray(
                    origin=self.position,
                    direction=self.direction.normalized(),
                    intensity=self.intensity / self.num_rays,
                    wavelength=self.wavelength
                ))

        return rays

    def _rotate_to_direction(self, local_dir: Vector3) -> Vector3:
        """Rotate local direction to align with source direction."""
        # Simple case: source direction is +z
        target = self.direction.normalized()

        if abs(target.dot(Vector3(0, 0, 1)) - 1.0) < 1e-10:
            return local_dir

        # Rotation axis and angle
        up = Vector3(0, 0, 1)
        axis = Vector3(
            up.y * target.z - up.z * target.y,
            up.z * target.x - up.x * target.z,
            up.x * target.y - up.y * target.x
        ).normalized()

        cos_angle = up.dot(target)
        angle = np.arccos(np.clip(cos_angle, -1, 1))

        # Rodrigues rotation
        if axis.magnitude() < 1e-10:
            return local_dir

        cos_a = np.cos(angle)
        sin_a = np.sin(angle)

        result = Vector3(
            local_dir.x * (cos_a + axis.x**2 * (1 - cos_a)) +
            local_dir.y * (axis.x * axis.y * (1 - cos_a) - axis.z * sin_a) +
            local_dir.z * (axis.x * axis.z * (1 - cos_a) + axis.y * sin_a),

            local_dir.x * (axis.y * axis.x * (1 - cos_a) + axis.z * sin_a) +
            local_dir.y * (cos_a + axis.y**2 * (1 - cos_a)) +
            local_dir.z * (axis.y * axis.z * (1 - cos_a) - axis.x * sin_a),

            local_dir.x * (axis.z * axis.x * (1 - cos_a) - axis.y * sin_a) +
            local_dir.y * (axis.z * axis.y * (1 - cos_a) + axis.x * sin_a) +
            local_dir.z * (cos_a + axis.z**2 * (1 - cos_a))
        )

        return result.normalized()


@dataclass
class Object3D:
    """3D object in non-sequential mode."""
    name: str = "Object"
    object_type: str = "sphere"  # sphere, cylinder, box, lens
    position: Vector3 = field(default_factory=Vector3)
    material: Optional[str] = None  # None = mirror/air
    coating: Optional[str] = None
    scatter_model: Optional[str] = None

    # Geometry parameters
    radius: float = 0.0  # For spheres/cylinders
    length: float = 0.0  # For cylinders/lenses
    half_width: float = 0.0  # For boxes
    half_height: float = 0.0

    # Lens specific
    radius1: float = 0.0
    radius2: float = 0.0
    thickness: float = 0.0

    # Interaction properties
    reflectivity: float = 0.0  # For mirrors
    transmission: float = 1.0  # For transmissive
    absorption: float = 0.0

    # Object ID (assigned by system)
    object_id: int = 0

    def intersect(self, ray: Ray) -> Optional[HitPoint]:
        """Find intersection with this object."""
        if self.object_type == "sphere":
            return self._intersect_sphere(ray)
        elif self.object_type == "cylinder":
            return self._intersect_cylinder(ray)
        elif self.object_type == "box":
            return self._intersect_box(ray)
        elif self.object_type == "lens":
            return self._intersect_lens(ray)
        return None

    def _intersect_sphere(self, ray: Ray) -> Optional[HitPoint]:
        """Ray-sphere intersection."""
        oc = ray.origin - self.position
        a = ray.direction.dot(ray.direction)
        b = 2.0 * oc.dot(ray.direction)
        c = oc.dot(oc) - self.radius**2
        discriminant = b**2 - 4 * a * c

        if discriminant < 0:
            return None

        sqrt_disc = np.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2 * a)
        t2 = (-b + sqrt_disc) / (2 * a)

        # Find nearest positive intersection
        t = None
        inside = False
        if t1 > 1e-10:
            t = t1
            inside = False
        elif t2 > 1e-10:
            t = t2
            inside = True
        else:
            return None

        point = ray.point_at(t)
        normal = (point - self.position).normalized()
        if inside:
            normal = Vector3(-normal.x, -normal.y, -normal.z)

        return HitPoint(
            ray=ray,
            object_id=self.object_id,
            point=point,
            normal=normal,
            distance=t,
            inside=inside
        )

    def _intersect_cylinder(self, ray: Ray) -> Optional[HitPoint]:
        """Ray-cylinder intersection (infinite cylinder along z-axis)."""
        # Transform ray to local coordinates
        local_origin = ray.origin - self.position
        local_dir = ray.direction

        # Solve quadratic for x² + y² = r²
        a = local_dir.x**2 + local_dir.y**2
        if abs(a) < 1e-15:
            return None

        b = 2 * (local_origin.x * local_dir.x + local_origin.y * local_dir.y)
        c = local_origin.x**2 + local_origin.y**2 - self.radius**2

        discriminant = b**2 - 4 * a * c
        if discriminant < 0:
            return None

        sqrt_disc = np.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2 * a)
        t2 = (-b + sqrt_disc) / (2 * a)

        # Find valid intersection within length
        for t in [t1, t2]:
            if t > 1e-10:
                point = ray.point_at(t)
                local_z = point.z - self.position.z
                if abs(local_z) <= self.length / 2:
                    # Valid intersection with cylinder body
                    normal = Vector3(
                        (point.x - self.position.x) / self.radius,
                        (point.y - self.position.y) / self.radius,
                        0
                    ).normalized()

                    if local_origin.x**2 + local_origin.y**2 > self.radius**2:
                        inside = False
                    else:
                        inside = True
                        normal = Vector3(-normal.x, -normal.y, -normal.z)

                    return HitPoint(
                        ray=ray,
                        object_id=self.object_id,
                        point=point,
                        normal=normal,
                        distance=t,
                        inside=inside
                    )

        return None

    def _intersect_box(self, ray: Ray) -> Optional[HitPoint]:
        """Ray-box intersection."""
        # Transform to local coordinates
        local_origin = ray.origin - self.position
        local_dir = ray.direction

        # Box bounds
        hx, hy, hz = self.half_width, self.half_height, self.length / 2

        # Find intersection with each pair of planes
        t_min = -np.inf
        t_max = np.inf
        normal = Vector3()

        # X planes
        if abs(local_dir.x) > 1e-15:
            t1 = (-hx - local_origin.x) / local_dir.x
            t2 = (hx - local_origin.x) / local_dir.x
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > t_min:
                t_min = t1
                normal = Vector3(-np.sign(local_dir.x), 0, 0)
            if t2 < t_max:
                t_max = t2
        elif abs(local_origin.x) > hx:
            return None

        # Y planes
        if abs(local_dir.y) > 1e-15:
            t1 = (-hy - local_origin.y) / local_dir.y
            t2 = (hy - local_origin.y) / local_dir.y
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > t_min:
                t_min = t1
                normal = Vector3(0, -np.sign(local_dir.y), 0)
            if t2 < t_max:
                t_max = t2
        elif abs(local_origin.y) > hy:
            return None

        # Z planes
        if abs(local_dir.z) > 1e-15:
            t1 = (-hz - local_origin.z) / local_dir.z
            t2 = (hz - local_origin.z) / local_dir.z
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > t_min:
                t_min = t1
                normal = Vector3(0, 0, -np.sign(local_dir.z))
            if t2 < t_max:
                t_max = t2
        elif abs(local_origin.z) > hz:
            return None

        if t_min > t_max or t_max < 1e-10:
            return None

        t = t_min if t_min > 1e-10 else t_max

        return HitPoint(
            ray=ray,
            object_id=self.object_id,
            point=ray.point_at(t),
            normal=normal,
            distance=t,
            inside=False
        )

    def _intersect_lens(self, ray: Ray) -> Optional[HitPoint]:
        """
        Ray-lens intersection. The lens is centred at ``position`` with its
        axis along z: front vertex at z - thickness/2 (radius1), back vertex
        at z + thickness/2 (radius2), clear semi-aperture ``radius`` (0 =
        limited only by the spheres). Only the two optical surfaces are
        modelled; a ray reaching the edge between them is not intercepted.
        Normals point out of the glass.
        """
        best = None
        zc = self.position.z
        for vz, R, outward_sign in ((zc - self.thickness / 2, self.radius1, -1.0),
                                    (zc + self.thickness / 2, self.radius2, +1.0)):
            hits = []
            if R == 0 or abs(R) >= 1e9:
                if abs(ray.direction.z) > 1e-15:
                    t = (vz - ray.origin.z) / ray.direction.z
                    if t > 1e-10:
                        hits.append((t, Vector3(0, 0, outward_sign)))
            else:
                centre = Vector3(self.position.x, self.position.y, vz + R)
                oc = ray.origin - centre
                b = 2.0 * oc.dot(ray.direction)
                c = oc.dot(oc) - R * R
                disc = b * b - 4 * c
                if disc >= 0:
                    for t in ((-b - np.sqrt(disc)) / 2, (-b + np.sqrt(disc)) / 2):
                        if t <= 1e-10:
                            continue
                        p = ray.point_at(t)
                        # keep the cap that contains the vertex
                        if (p.z - centre.z) * (-R) < 0:
                            continue
                        n = (p - centre).normalized()
                        if n.z * outward_sign < 0:
                            n = Vector3(-n.x, -n.y, -n.z)
                        hits.append((t, n))
            for t, n in hits:
                p = ray.point_at(t)
                r_perp = np.hypot(p.x - self.position.x, p.y - self.position.y)
                if self.radius and r_perp > self.radius:
                    continue
                if best is None or t < best[0]:
                    best = (t, n)
        if best is None:
            return None
        t, n = best
        inside = ray.direction.dot(n) > 0     # leaving the glass
        return HitPoint(ray=ray, object_id=self.object_id, point=ray.point_at(t),
                        normal=n, distance=t, inside=inside)


@dataclass
class Detector:
    """Detector object for collecting rays."""
    name: str = "Detector"
    position: Vector3 = field(default_factory=lambda: Vector3(0, 0, 100))
    normal: Vector3 = field(default_factory=lambda: Vector3(0, 0, -1))
    width: float = 25.0  # mm
    height: float = 25.0  # mm
    pixels_x: int = 100
    pixels_y: int = 100

    # Collected data
    irradiance: np.ndarray = None  # type: ignore[assignment]  # set in __post_init__
    counts: np.ndarray = None  # type: ignore[assignment]  # set in __post_init__
    total_power: float = 0.0
    num_rays_hit: int = 0

    def __post_init__(self):
        if self.irradiance is None:
            self.irradiance = np.zeros((self.pixels_y, self.pixels_x))
        if self.counts is None:
            self.counts = np.zeros((self.pixels_y, self.pixels_x))

    def reset(self):
        """Clear collected data."""
        self.irradiance[:] = 0
        self.counts[:] = 0
        self.total_power = 0.0
        self.num_rays_hit = 0

    def _basis(self):
        n = self.normal.normalized()
        ref = Vector3(1, 0, 0) if abs(n.x) < 0.9 else Vector3(0, 1, 0)
        u = Vector3(ref.y * n.z - ref.z * n.y, ref.z * n.x - ref.x * n.z,
                    ref.x * n.y - ref.y * n.x).normalized()
        v = Vector3(n.y * u.z - n.z * u.y, n.z * u.x - n.x * u.z, n.x * u.y - n.y * u.x)
        return n, u, v

    def hit_distance(self, ray: Ray) -> Optional[float]:
        """Distance along the ray to the detector's active area (front side
        only: the normal faces the incoming light), or None."""
        n, u, v = self._basis()
        dn = ray.direction.dot(n)
        if dn >= 0:
            return None
        t = (self.position - ray.origin).dot(n) / dn
        if t <= 0:
            return None
        rel = ray.point_at(t) - self.position
        if abs(rel.dot(u)) > self.width / 2 or abs(rel.dot(v)) > self.height / 2:
            return None
        return t

    def process_ray(self, ray: Ray):
        """Deposit a ray that reaches the detector's front face."""
        t = self.hit_distance(ray)
        if t is not None:
            n, u, v = self._basis()
            rel = ray.point_at(t) - self.position
            # equal-width pixels across the active area
            px = int(np.floor((rel.dot(u) / self.width + 0.5) * self.pixels_x))
            py = int(np.floor((rel.dot(v) / self.height + 0.5) * self.pixels_y))
            px = max(0, min(self.pixels_x - 1, px))
            py = max(0, min(self.pixels_y - 1, py))
            pixel_area = (self.width / self.pixels_x) * (self.height / self.pixels_y)
            # irradiance = power per unit area (power units / length units^2)
            self.irradiance[py, px] += ray.intensity / pixel_area
            self.counts[py, px] += 1
            self.total_power += ray.intensity
            self.num_rays_hit += 1


@dataclass
class NSCSystem:
    """Non-sequential optical system."""
    sources: list[Source] = field(default_factory=list)
    objects: list[Object3D] = field(default_factory=list)
    detectors: list[Detector] = field(default_factory=list)

    # Tracing parameters
    max_order: int = 10
    min_intensity: float = 1e-6

    def add_source(self, source: Source) -> int:
        """Add a source to the system."""
        self.sources.append(source)
        return len(self.sources) - 1

    def add_object(self, obj: Object3D) -> int:
        """Add an object to the system."""
        obj.object_id = len(self.objects)
        self.objects.append(obj)
        return obj.object_id

    def add_detector(self, detector: Detector) -> int:
        """Add a detector to the system."""
        self.detectors.append(detector)
        return len(self.detectors) - 1

    def reset_detectors(self):
        """Clear all detector data."""
        for det in self.detectors:
            det.reset()
