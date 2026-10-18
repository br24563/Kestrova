"""
Non-sequential ray tracer.

Traces rays through a system of 3D objects, handling splitting at interfaces,
scattering, and detector collection.
"""

from typing import Optional
import numpy as np
from .system import (
    NSCSystem, Ray, HitPoint, Vector3, Source, Detector, Object3D
)
from .scatter import ScatterModel, NoScatter


class NSCTracer:
    """Non-sequential ray tracer."""

    def __init__(self, system: NSCSystem):
        self.system = system
        self.scatter_models: dict[str, ScatterModel] = {}

    def register_scatter_model(self, name: str, model: ScatterModel):
        """Register a scattering model."""
        self.scatter_models[name] = model

    def trace(self) -> dict:
        """Trace all sources through the system."""
        # Reset detectors
        self.system.reset_detectors()

        # Trace rays from each source
        for source in self.system.sources:
            rays = source.generate_rays()
            for ray in rays:
                self._trace_ray(ray)

        # Collect results
        return self._collect_results()

    def _trace_ray(self, ray: Ray, depth: int = 0):
        """Trace a single ray through the system."""
        # Check termination conditions
        if depth >= self.system.max_order:
            return
        if ray.intensity < self.system.min_intensity:
            return

        # Find nearest intersection
        nearest_hit = None
        nearest_obj = None

        for obj in self.system.objects:
            hit = obj.intersect(ray)
            if hit and (nearest_hit is None or hit.distance < nearest_hit.distance):
                nearest_hit = hit
                nearest_obj = obj

        # A detector closer than the nearest object absorbs the ray.
        det_hits = [(d.hit_distance(ray), d) for d in self.system.detectors]
        det_hits = [(t, d) for t, d in det_hits if t is not None]
        if det_hits:
            t_det, det = min(det_hits, key=lambda x: x[0])
            if nearest_hit is None or t_det < nearest_hit.distance:
                det.process_ray(ray)
                return
        if nearest_hit is None:
            return

        # Process hit
        self._process_hit(ray, nearest_hit, nearest_obj, depth)

    def _process_hit(self, ray: Ray, hit: HitPoint, obj: Object3D, depth: int):
        """Process a ray-object intersection."""
        # Determine interaction type
        if obj.material is None:
            # Mirror or air
            self._process_mirror(ray, hit, obj, depth)
        elif obj.scatter_model:
            # Scattering surface
            self._process_scatter(ray, hit, obj, depth)
        else:
            # Refractive surface - split ray
            self._process_refraction(ray, hit, obj, depth)

    def _process_mirror(self, ray: Ray, hit: HitPoint, obj: Object3D, depth: int):
        """Process reflection from a mirror surface."""
        # Calculate reflected direction
        normal = hit.normal
        incident = ray.direction

        # Reflected direction: r = d - 2(d·n)n
        dot = incident.dot(normal)
        reflected = Vector3(
            incident.x - 2 * dot * normal.x,
            incident.y - 2 * dot * normal.y,
            incident.z - 2 * dot * normal.z
        ).normalized()

        # Create reflected ray
        reflected_ray = Ray(
            origin=hit.point,
            direction=reflected,
            intensity=ray.intensity * obj.reflectivity,
            wavelength=ray.wavelength,
            order=ray.order + 1,
            path_length=ray.path_length + hit.distance
        )

        # Continue tracing
        self._trace_ray(reflected_ray, depth + 1)

    def _process_scatter(self, ray: Ray, hit: HitPoint, obj: Object3D, depth: int):
        """Process scattering from a surface."""
        model = self.scatter_models.get(obj.scatter_model)
        if model is None:
            return

        # Generate scattered rays
        scattered_rays = model.scatter(ray, hit)

        for scattered_ray in scattered_rays:
            self._trace_ray(scattered_ray, depth + 1)

    def _process_refraction(self, ray: Ray, hit: HitPoint, obj: Object3D, depth: int):
        """Process refraction at a surface (split into reflected and transmitted)."""
        from optics.materials_expanded import refractive_index

        # Indices: objects sit in air; a ray leaving the object goes glass -> air.
        n_obj = refractive_index(obj.material, ray.wavelength) if obj.material else 1.0
        n1, n2 = (n_obj, 1.0) if hit.inside else (1.0, n_obj)

        # Orient the normal against the incoming ray.
        normal = hit.normal
        if ray.direction.dot(normal) > 0:
            normal = Vector3(-normal.x, -normal.y, -normal.z)

        cos_i = -ray.direction.dot(normal)
        sin_t2 = (n1 / n2)**2 * (1 - cos_i**2)

        # Total internal reflection
        if sin_t2 > 1.0:
            self._process_mirror(ray, hit, obj, depth)
            return

        cos_t = np.sqrt(1 - sin_t2)

        # Fresnel equations
        rs = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t))**2
        rp = ((n1 * cos_t - n2 * cos_i) / (n1 * cos_t + n2 * cos_i))**2
        reflectance = (rs + rp) / 2
        transmittance = 1 - reflectance

        # Reflected ray (rays below min_intensity are dropped by _trace_ray)
        if reflectance > 0:
            dot = ray.direction.dot(normal)
            reflected = Vector3(
                ray.direction.x - 2 * dot * normal.x,
                ray.direction.y - 2 * dot * normal.y,
                ray.direction.z - 2 * dot * normal.z
            ).normalized()

            reflected_ray = Ray(
                origin=hit.point,
                direction=reflected,
                intensity=ray.intensity * reflectance * (1 - obj.absorption),
                wavelength=ray.wavelength,
                order=ray.order + 1,
                path_length=ray.path_length + hit.distance
            )
            self._trace_ray(reflected_ray, depth + 1)

        # Transmitted ray: t = r d + (r cos_i - cos_t) n, n facing the ray
        if transmittance > 0:
            ratio = n1 / n2
            k = ratio * cos_i - cos_t
            transmitted = Vector3(
                ratio * ray.direction.x + k * normal.x,
                ratio * ray.direction.y + k * normal.y,
                ratio * ray.direction.z + k * normal.z
            ).normalized()

            transmitted_ray = Ray(
                origin=hit.point,
                direction=transmitted,
                intensity=ray.intensity * transmittance * (1 - obj.absorption),
                wavelength=ray.wavelength,
                order=ray.order,
                path_length=ray.path_length + hit.distance
            )
            self._trace_ray(transmitted_ray, depth + 1)

    def _collect_results(self) -> dict:
        """Collect tracing results."""
        results = {
            'detectors': [],
            'total_rays_traced': 0,
            'total_power_collected': 0.0
        }

        for i, detector in enumerate(self.system.detectors):
            results['detectors'].append({
                'id': i,
                'name': detector.name,
                'num_rays_hit': detector.num_rays_hit,
                'total_power': detector.total_power,
                'peak_irradiance': float(np.max(detector.irradiance)) if detector.irradiance.size > 0 else 0,
                'irradiance_map': detector.irradiance.tolist()
            })
            results['total_power_collected'] += detector.total_power

        return results
