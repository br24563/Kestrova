"""
Performance and Scalability for Optical Design.

Implements:
- Parallel ray tracing (multi-threaded and multi-process)
- BSP/kd-tree acceleration for non-sequential ray tracing
- Ray trace result caching (memoization)
- Performance benchmarking utilities

All values are in SI base units (meters, radians).
"""

import math
import time
import hashlib
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

import numpy as np

from .models import OpticalSystem, Ray
from .real_rays import trace_real_ray


def _trace_one(system, ray):
    return trace_real_ray(system, ray)


def trace_rays_parallel(system, rays, max_workers=None, use_processes=False):
    """Trace multiple rays in parallel using thread or process pools."""
    from functools import partial

    if not rays:
        return []
    if max_workers is None:
        import os

        max_workers = os.cpu_count() or 4
    max_workers = max(1, min(max_workers, len(rays)))
    if use_processes:
        import multiprocessing

        # "spawn", not the Linux default "fork": forking a process whose
        # compiled ray kernels have started threads can kill the workers
        pool_cm = ProcessPoolExecutor(
            max_workers=max_workers, mp_context=multiprocessing.get_context("spawn")
        )
    else:
        pool_cm = ThreadPoolExecutor(max_workers=max_workers)
    with pool_cm as pool:
        # a module-level function (not a lambda) so process pools can pickle it
        return list(pool.map(partial(_trace_one, system), rays))


def trace_rays_batched(system, rays, batch_size=100):
    """Trace rays in batches to limit memory usage."""
    all_paths = []
    for i in range(0, len(rays), batch_size):
        all_paths.extend(trace_rays_parallel(system, rays[i : i + batch_size]))
    return all_paths


class RayTraceCache:
    """LRU cache for ray tracing results."""

    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def _system_hash(self, system):
        comps = [c.model_dump() for c in system.components]
        # the analysis settings matter: a ThinLens focal length is defined at
        # the analysis wavelength
        data = (
            repr(comps)
            + repr(system.object.model_dump())
            + repr(system.image_plane.model_dump())
            + repr(system.analysis_settings.model_dump())
        )
        return hashlib.md5(data.encode()).hexdigest()

    def _ray_key(self, sys_hash, ray):
        return (
            sys_hash
            + "|"
            + str(round(ray.y, 12))
            + "|"
            + str(round(ray.theta, 12))
            + "|"
            + str(round(ray.z, 12))
            + "|"
            + str(round(ray.wavelength, 12))
        )

    def trace(self, system, ray):
        """Trace a ray with caching."""
        sys_hash = self._system_hash(system)
        key = self._ray_key(sys_hash, ray)
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        path = trace_real_ray(system, ray)
        if len(self.cache) >= self.max_size:
            del self.cache[next(iter(self.cache))]
        self.cache[key] = path
        return path

    def clear(self):
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    @property
    def hit_rate(self):
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def stats(self):
        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate,
        }


class AABB:
    """Axis-aligned bounding box for spatial acceleration."""

    def __init__(self):
        self.min_x = self.min_y = self.min_z = 1e30
        self.max_x = self.max_y = self.max_z = -1e30

    def expand(self, points):
        for x, y, z in points:
            self.min_x = min(self.min_x, x)
            self.min_y = min(self.min_y, y)
            self.min_z = min(self.min_z, z)
            self.max_x = max(self.max_x, x)
            self.max_y = max(self.max_y, y)
            self.max_z = max(self.max_z, z)

    def intersects_ray(self, origin, direction):
        """Ray-box intersection test using the slab method."""
        ox, oy, oz = origin
        dx, dy, dz = direction
        tmin = 0.0
        tmax = 1e30
        slabs = (
            (ox, dx, self.min_x, self.max_x),
            (oy, dy, self.min_y, self.max_y),
            (oz, dz, self.min_z, self.max_z),
        )
        for o, d, lo, hi in slabs:
            if abs(d) < 1e-15:
                if o < lo or o > hi:
                    return False
            else:
                t1 = (lo - o) / d
                t2 = (hi - o) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                tmin = max(tmin, t1)
                tmax = min(tmax, t2)
                if tmin > tmax:
                    return False
        return True


class BSPNode:
    """Binary space partitioning node for non-sequential acceleration."""

    def __init__(self, depth=0, max_depth=10, max_objects=8):
        self.depth = depth
        self.max_depth = max_depth
        self.max_objects = max_objects
        self.bounds = AABB()
        self.children = None
        self.objects = []

    def is_leaf(self):
        return self.children is None

    def build(self, objects, get_bounds):
        """Recursively partition objects into a BSP tree."""
        if not objects:
            return True
        for obj in objects:
            b = get_bounds(obj)
            if b is not None:
                self.bounds.expand([(b[0], b[1], b[2]), (b[3], b[4], b[5])])
        self.objects = objects
        if self.depth >= self.max_depth or len(objects) <= self.max_objects:
            return True
        mid_x = self.bounds.min_x + (self.bounds.max_x - self.bounds.min_x) / 2.0
        left = []
        right = []
        for obj in objects:
            b = get_bounds(obj)
            if b is None:
                left.append(obj)
                continue
            cx = (b[0] + b[3]) / 2.0
            if cx < mid_x:
                left.append(obj)
            else:
                right.append(obj)
        if not left or not right:
            return True
        self.children = (
            BSPNode(self.depth + 1, self.max_depth, self.max_objects),
            BSPNode(self.depth + 1, self.max_depth, self.max_objects),
        )
        self.children[0].build(left, get_bounds)
        self.children[1].build(right, get_bounds)
        return True

    def query_ray(self, origin, direction, results):
        """Collect objects whose bounds intersect the ray."""
        if not self.bounds.intersects_ray(origin, direction):
            return
        if self.is_leaf():
            results.extend(self.objects)
            return
        for child in self.children:
            child.query_ray(origin, direction, results)


class SpatialAccelerator:
    """Spatial acceleration structure for NSC ray tracing."""

    def __init__(self, max_depth=12, max_objects=4):
        self.root = BSPNode(max_depth=max_depth, max_objects=max_objects)
        self.built = False

    def build(self, objects):
        """Build the BSP tree from a list of objects."""

        def get_bounds(obj):
            p = getattr(obj, "position", None)
            if p is None:
                return None
            r = getattr(obj, "aperture_radius", 0.1)
            return (p.x - r, p.y - r, p.z - r, p.x + r, p.y + r, p.z + r)

        self.root.build(objects, get_bounds)
        self.built = True

    def query(self, origin, direction):
        """Return candidate objects along a ray."""
        results = []
        self.root.query_ray(origin, direction, results)
        return results


@dataclass
class BenchmarkResult:
    """Result of a performance benchmark."""

    name: str
    duration_s: float
    rays_traced: int
    rays_per_second: float
    cache_hit_rate: float = 0.0
    notes: list = field(default_factory=list)


def benchmark_ray_tracing(system, num_rays=1000, use_cache=True, parallel=True):
    """Benchmark ray tracing performance on a system."""
    rays = []
    for i in range(num_rays):
        y = 0.0125 * (2.0 * np.random.random() - 1.0)
        theta = 0.1 * (2.0 * np.random.random() - 1.0)
        rays.append(
            Ray(
                y=y,
                theta=theta,
                z=system.object.position,
                wavelength=550e-9,
                ray_type="fill",
            )
        )

    cache = RayTraceCache(max_size=max(100, num_rays * 2))

    # Warm up the first few rays
    warm = rays[:10]
    for ray in warm:
        if use_cache:
            cache.trace(system, ray)
        else:
            trace_real_ray(system, ray)

    start = time.perf_counter()
    if use_cache:
        for ray in rays:
            cache.trace(system, ray)
    elif parallel:
        trace_rays_parallel(system, rays)
    else:
        for ray in rays:
            trace_real_ray(system, ray)
    end = time.perf_counter()

    duration = end - start
    rps = num_rays / duration if duration > 0 else float("inf")
    notes = []
    if use_cache:
        notes.append("Cache hit rate: " + str(round(cache.hit_rate, 4)))

    return BenchmarkResult(
        name="ray_tracing",
        duration_s=duration,
        rays_traced=num_rays,
        rays_per_second=rps,
        cache_hit_rate=cache.hit_rate if use_cache else 0.0,
        notes=notes,
    )


def benchmark_all(system, num_rays=500):
    """Run all ray tracing benchmarks and return results."""
    return [
        benchmark_ray_tracing(system, num_rays, use_cache=False, parallel=False),
        benchmark_ray_tracing(system, num_rays, use_cache=True, parallel=False),
        benchmark_ray_tracing(system, num_rays, use_cache=False, parallel=True),
    ]
