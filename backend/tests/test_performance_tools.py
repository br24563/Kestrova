"""
Tests for the performance utilities (optics.performance).

References are independent of the code under test:
- parallel and batched tracing must equal tracing each ray serially;
- the cache must return the serial result, miss when the system changes
  and evict the oldest entry first;
- ray/box hits are decided here by hand for rays parallel to an axis
  (inside the box's cross-section and the box ahead of the ray), and the
  BSP query must never miss an object such a ray passes through.
"""

import math
import random
from types import SimpleNamespace

import pytest

from optics.models import Ray
from optics.performance import (
    AABB,
    BSPNode,
    RayTraceCache,
    SpatialAccelerator,
    benchmark_all,
    benchmark_ray_tracing,
    trace_rays_batched,
    trace_rays_parallel,
)
from optics.presets import get_preset_by_id
from optics.real_rays import trace_real_ray


def system():
    return get_preset_by_id("thick_lens")["system"]


def rays(n=12):
    return [Ray(y=0.004 * (k / n - 0.5), theta=0.01 * math.sin(k), z=0.0,
                wavelength=550e-9) for k in range(n)]


class TestParallelTracing:

    def test_threads_match_serial(self):
        s, rs = system(), rays()
        serial = [trace_real_ray(s, r) for r in rs]
        assert trace_rays_parallel(s, rs, max_workers=3) == serial
        assert trace_rays_parallel(s, rs) == serial
        assert trace_rays_batched(s, rs, batch_size=5) == serial

    def test_processes_match_serial(self):
        s, rs = system(), rays(3)
        assert trace_rays_parallel(s, rs, max_workers=2, use_processes=True) == [
            trace_real_ray(s, r) for r in rs
        ]

    def test_no_rays(self):
        assert trace_rays_parallel(system(), []) == []


class TestCache:

    def test_hits_return_the_serial_result(self):
        s, rs = system(), rays(4)
        cache = RayTraceCache()
        first = [cache.trace(s, r) for r in rs]
        again = [cache.trace(s, r) for r in rs]
        assert first == again == [trace_real_ray(s, r) for r in rs]
        assert cache.stats == {"size": 4, "hits": 4, "misses": 4, "hit_rate": 0.5}

    def test_a_changed_system_misses(self):
        s = system()
        r = rays(1)[0]
        cache = RayTraceCache()
        cache.trace(s, r)
        moved = s.model_copy(update={"image_plane": s.image_plane.model_copy(
            update={"position": s.image_plane.position + 0.01})})
        path = cache.trace(moved, r)
        assert cache.misses == 2
        assert path == trace_real_ray(moved, r)

    def test_oldest_entry_is_evicted(self):
        s, rs = system(), rays(3)
        cache = RayTraceCache(max_size=2)
        for r in rs:
            cache.trace(s, r)
        assert cache.stats["size"] == 2
        cache.trace(s, rs[0])  # evicted: a miss
        cache.trace(s, rs[2])  # still cached: a hit
        assert (cache.hits, cache.misses) == (1, 4)
        cache.clear()
        assert cache.stats == {"size": 0, "hits": 0, "misses": 0, "hit_rate": 0.0}


def box(cx, cy, cz, r):
    return SimpleNamespace(position=SimpleNamespace(x=cx, y=cy, z=cz), aperture_radius=r)


def z_ray_hits(obj, x, y, z0, forward=True):
    """A ray along +z (or -z) from (x, y, z0) meets the object's box."""
    p, r = obj.position, obj.aperture_radius
    if abs(x - p.x) > r or abs(y - p.y) > r:
        return False
    return (p.z + r >= z0) if forward else (p.z - r <= z0)


class TestSpatial:

    def test_aabb_slab_test(self):
        b = AABB()
        b.expand([(-1, -1, 2), (1, 1, 4)])
        assert b.intersects_ray((0, 0, 0), (0, 0, 1))
        assert not b.intersects_ray((0, 0, 0), (0, 0, -1))  # box behind the ray
        assert not b.intersects_ray((2, 0, 0), (0, 0, 1))  # parallel, outside
        assert b.intersects_ray((-5, 0, 3), (1, 0, 0))
        assert b.intersects_ray((-3, -3, 0), (1, 1, 1))  # enters at (-1, -1, 2)
        assert not b.intersects_ray((-3, 3, 0), (1, 1, 1))

    def test_bsp_query_never_misses_a_hit(self):
        rng = random.Random(4)
        objs = [box(rng.uniform(-5, 5), rng.uniform(-5, 5), rng.uniform(-5, 5),
                    rng.uniform(0.1, 0.6)) for _ in range(60)]
        objs.append(SimpleNamespace(name="no position"))
        acc = SpatialAccelerator(max_depth=8, max_objects=3)
        acc.build(objs)
        assert acc.built and not acc.root.is_leaf()
        for _ in range(200):
            x, y, z0 = rng.uniform(-5, 5), rng.uniform(-5, 5), rng.uniform(-6, 6)
            fwd = rng.random() < 0.5
            found = acc.query((x, y, z0), (0, 0, 1 if fwd else -1))
            hits = [o for o in objs[:-1] if z_ray_hits(o, x, y, z0, fwd)]
            assert all(any(h is f for f in found) for h in hits)

    def test_small_or_empty_trees_are_leaves(self):
        node = BSPNode(max_objects=8)
        assert node.build([], lambda o: None) and node.is_leaf()
        objs = [box(0, 0, 0, 1), box(0.1, 0, 0, 1)]
        node.build(objs, lambda o: (o.position.x - 1, -1, -1, o.position.x + 1, 1, 1))
        assert node.is_leaf()
        results: list = []
        node.query_ray((0, 0, -5), (0, 0, 1), results)
        assert results == objs


class TestBenchmarks:

    @pytest.mark.parametrize("use_cache,parallel", [(True, False), (False, False),
                                                    (False, True)])
    def test_benchmark_reports_its_run(self, use_cache, parallel):
        r = benchmark_ray_tracing(system(), num_rays=20, use_cache=use_cache,
                                  parallel=parallel)
        assert r.rays_traced == 20
        assert r.duration_s > 0
        assert r.rays_per_second == pytest.approx(20 / r.duration_s)
        # 10 warm-up rays are traced first: with the cache they hit
        assert r.cache_hit_rate == (pytest.approx(10 / 30) if use_cache else 0.0)

    def test_benchmark_all(self):
        assert [b.name for b in benchmark_all(system(), num_rays=12)] == ["ray_tracing"] * 3
