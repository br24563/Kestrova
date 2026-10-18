"""
Tests for non-sequential ray tracing.
"""

import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.nsc import (
    Vector3, Ray, HitPoint,
    Source, Detector, Object3D, NSCSystem,
    NSCTracer,
    LambertianScatter, GaussianScatter, ABgScatter
)


class TestVector3:
    """Tests for 3D vector operations."""
    
    def test_addition(self):
        v1 = Vector3(1, 2, 3)
        v2 = Vector3(4, 5, 6)
        result = v1 + v2
        assert result.x == 5
        assert result.y == 7
        assert result.z == 9
    
    def test_subtraction(self):
        v1 = Vector3(4, 5, 6)
        v2 = Vector3(1, 2, 3)
        result = v1 - v2
        assert result.x == 3
        assert result.y == 3
        assert result.z == 3
    
    def test_scalar_multiplication(self):
        v = Vector3(1, 2, 3)
        result = v * 2
        assert result.x == 2
        assert result.y == 4
        assert result.z == 6
    
    def test_magnitude(self):
        v = Vector3(3, 4, 0)
        assert v.magnitude() == pytest.approx(5.0)
    
    def test_normalized(self):
        v = Vector3(3, 4, 0)
        n = v.normalized()
        assert n.magnitude() == pytest.approx(1.0)
    
    def test_dot_product(self):
        v1 = Vector3(1, 0, 0)
        v2 = Vector3(0, 1, 0)
        assert v1.dot(v2) == pytest.approx(0.0)
        
        v3 = Vector3(1, 0, 0)
        assert v1.dot(v3) == pytest.approx(1.0)


class TestRay:
    """Tests for ray operations."""
    
    def test_point_at(self):
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1)
        )
        point = ray.point_at(10)
        assert point.x == 0
        assert point.y == 0
        assert point.z == 10


class TestSource:
    """Tests for ray sources."""
    
    def test_point_source(self):
        source = Source(
            name="Test",
            position=Vector3(0, 0, 0),
            num_rays=100,
            source_type="point"
        )
        rays = source.generate_rays()
        assert len(rays) == 100
        for ray in rays:
            assert ray.direction.magnitude() == pytest.approx(1.0, abs=0.01)
    
    def test_collimated_source(self):
        source = Source(
            name="Test",
            position=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1),
            num_rays=10,
            source_type="collimated"
        )
        rays = source.generate_rays()
        assert len(rays) == 10
        for ray in rays:
            assert ray.direction.z == pytest.approx(1.0, abs=0.01)


class TestObject3D:
    """Tests for 3D objects."""
    
    def test_sphere_intersection(self):
        sphere = Object3D(
            object_type="sphere",
            position=Vector3(0, 0, 10),
            radius=5
        )
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1)
        )
        hit = sphere.intersect(ray)
        assert hit is not None
        assert hit.point.z == pytest.approx(5.0, abs=0.01)
    
    def test_sphere_no_intersection(self):
        sphere = Object3D(
            object_type="sphere",
            position=Vector3(0, 0, 10),
            radius=1
        )
        ray = Ray(
            origin=Vector3(10, 0, 0),
            direction=Vector3(0, 0, 1)
        )
        hit = sphere.intersect(ray)
        assert hit is None
    
    def test_box_intersection(self):
        box = Object3D(
            object_type="box",
            position=Vector3(0, 0, 10),
            half_width=5,
            half_height=5,
            length=10
        )
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1)
        )
        hit = box.intersect(ray)
        assert hit is not None
        assert hit.point.z == pytest.approx(5.0, abs=0.01)


class TestDetector:
    """Tests for detector objects."""
    
    def test_detector_creation(self):
        det = Detector(
            name="Test",
            position=Vector3(0, 0, 100),
            width=25,
            height=25,
            pixels_x=100,
            pixels_y=100
        )
        assert det.irradiance.shape == (100, 100)
        assert det.total_power == 0
    
    def test_detector_reset(self):
        det = Detector(
            name="Test",
            position=Vector3(0, 0, 100)
        )
        det.total_power = 10.0
        det.reset()
        assert det.total_power == 0


class TestNSCSystem:
    """Tests for non-sequential system."""
    
    def test_add_source(self):
        system = NSCSystem()
        source = Source(name="Test")
        idx = system.add_source(source)
        assert idx == 0
        assert len(system.sources) == 1
    
    def test_add_object(self):
        system = NSCSystem()
        obj = Object3D(object_type="sphere", radius=10)
        idx = system.add_object(obj)
        assert idx == 0
        assert len(system.objects) == 1
    
    def test_add_detector(self):
        system = NSCSystem()
        det = Detector(name="Test")
        idx = system.add_detector(det)
        assert idx == 0
        assert len(system.detectors) == 1


class TestNSCTracer:
    """Tests for non-sequential ray tracing."""
    
    def test_basic_trace(self):
        system = NSCSystem()
        
        # Add source
        source = Source(
            name="Source",
            position=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1),
            num_rays=100,
            source_type="collimated"
        )
        system.add_source(source)
        
        # Add detector
        detector = Detector(
            name="Detector",
            position=Vector3(0, 0, 100),
            width=25,
            height=25,
            pixels_x=50,
            pixels_y=50
        )
        system.add_detector(detector)
        
        # Trace
        tracer = NSCTracer(system)
        results = tracer.trace()
        
        assert 'detectors' in results
        assert len(results['detectors']) == 1
    
    def test_mirror_reflection(self):
        system = NSCSystem()
        
        # Add source
        source = Source(
            name="Source",
            position=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1),
            num_rays=10,
            source_type="collimated"
        )
        system.add_source(source)
        
        # Add mirror
        mirror = Object3D(
            name="Mirror",
            object_type="sphere",
            position=Vector3(0, 0, 50),
            radius=25,
            reflectivity=0.95
        )
        system.add_object(mirror)
        
        # Add detector
        detector = Detector(
            name="Detector",
            position=Vector3(0, 0, 100),
            width=50,
            height=50
        )
        system.add_detector(detector)
        
        # Trace
        tracer = NSCTracer(system)
        results = tracer.trace()
        
        # Should have some results
        assert results is not None


class TestScatterModels:
    """Tests for scattering models."""
    
    def test_lambertian_scatter(self):
        model = LambertianScatter(num_rays=10, reflectance=0.1)
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1),
            intensity=1.0
        )
        hit = HitPoint(
            ray=ray,
            object_id=0,
            point=Vector3(0, 0, 10),
            normal=Vector3(0, 0, -1),
            distance=10,
            inside=False
        )
        scattered = model.scatter(ray, hit)
        assert len(scattered) == 10
    
    def test_gaussian_scatter(self):
        model = GaussianScatter(num_rays=10, sigma=5.0, reflectance=0.1)
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1),
            intensity=1.0
        )
        hit = HitPoint(
            ray=ray,
            object_id=0,
            point=Vector3(0, 0, 10),
            normal=Vector3(0, 0, -1),
            distance=10,
            inside=False
        )
        scattered = model.scatter(ray, hit)
        assert len(scattered) == 10
    
    def test_abg_scatter(self):
        model = ABgScatter(num_rays=10, A=0.01, B=0.01, G=2.0)
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1),
            intensity=1.0
        )
        hit = HitPoint(
            ray=ray,
            object_id=0,
            point=Vector3(0, 0, 10),
            normal=Vector3(0, 0, -1),
            distance=10,
            inside=False
        )
        scattered = model.scatter(ray, hit)
        assert len(scattered) == 10


class TestAsphericSurfaces:
    """Tests for aspheric surface support."""
    
    def test_even_asphere_sag(self):
        """Test even aspheric sag calculation."""
        from optics.nsc import AsphericSurface
        
        asphere = AsphericSurface(
            radius=50.0,
            conic=0.0,  # Sphere
            aspheric_coeffs=[0, 0, 0, 0, 0]
        )
        
        # At center, sag should be 0
        assert asphere.sag(0) == pytest.approx(0.0, abs=0.01)
        
        # At edge, sag should be positive
        sag_edge = asphere.sag(25.0)
        assert sag_edge > 0
    
    def test_asphere_intersection(self):
        """Test ray-asphere intersection."""
        from optics.nsc import AsphericSurface
        
        asphere = AsphericSurface(
            name="Test",
            position=Vector3(0, 0, 50),
            radius=50.0,
            conic=0.0,
            aperture_radius=25.0
        )
        asphere.object_id = 0
        
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1)
        )
        
        hit = asphere.intersect(ray)
        assert hit is not None
        assert hit.point.z > 0
    
    def test_odd_asphere(self):
        """Test odd aspheric surface."""
        from optics.nsc import OddAsphericSurface
        
        asphere = OddAsphericSurface(
            radius=50.0,
            conic=0.0,
            odd_coeffs=[1e-6, 1e-8]
        )
        
        # Should calculate sag without error
        sag = asphere.sag(10.0)
        assert math.isfinite(sag)
    
    def test_qtype_surface(self):
        """Test Q-type aspheric surface."""
        from optics.nsc import QTypeSurface
        
        qsurf = QTypeSurface(
            radius=50.0,
            conic=0.0,
            q_type="Qbfs",
            coefficients=[0.1, 0.01]
        )
        
        # Should calculate sag without error
        sag = qsurf.sag(10.0)
        assert math.isfinite(sag)
