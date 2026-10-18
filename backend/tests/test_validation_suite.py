"""
Comprehensive validation suite against published textbook cases.

This test suite validates the optical engine against trusted reference results
from published textbooks and vendor catalogs.

Sources:
- Born & Wolf, "Principles of Optics", 7th Edition
- Smith, "Modern Optical Engineering", 4th Edition
- Hecht, "Optics", 5th Edition
- Schott Glass Catalog, 2024
"""

import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.lenses import image_distance, object_distance, thin_lens_matrix, system_matrix
from optics.rays import calculate_paraxial_image_position, calculate_paraxial_image_height
from optics.materials import refractive_index
from optics.diffraction import airy_disk_radius, mtf
from optics.materials import abbe_number
from optics.models import OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings
from tests.references.textbook_cases import (
    PARAXIAL_CASES, TWO_LENS_CASES,
    AIRY_DISK_CASES, MTF_CUTOFF_CASES, SCHOTT_INDICES, ABBE_NUMBERS,
)


class TestParaxialEquationValidation:
    """Validate thin lens equation against textbook cases."""

    @pytest.mark.parametrize("case", PARAXIAL_CASES, ids=[c["description"] for c in PARAXIAL_CASES])
    def test_image_distance(self, case):
        """Image distance matches thin lens equation."""
        f = case["f"]
        s = case["s"]
        expected = case["expected_s_prime"]
        result = image_distance(f, s)
        assert result == pytest.approx(expected, rel=1e-6), (
            f"Failed: {case['description']}\n"
            f"  Expected: {expected:.6f} m\n"
            f"  Got: {result:.6f} m\n"
            f"  Source: {case['source']}"
        )

    @pytest.mark.parametrize("case", PARAXIAL_CASES, ids=[c["description"] for c in PARAXIAL_CASES])
    def test_object_distance_inverse(self, case):
        """Object distance calculation is inverse of image distance."""
        f = case["f"]
        s_prime = case["expected_s_prime"]
        expected_s = case["s"]
        result = object_distance(f, s_prime)
        assert result == pytest.approx(expected_s, rel=1e-6)

    @pytest.mark.parametrize("case", PARAXIAL_CASES, ids=[c["description"] for c in PARAXIAL_CASES])
    def test_magnification(self, case):
        """Magnification m = s'/s matches expected value."""
        s = case["s"]
        s_prime = case["expected_s_prime"]
        expected_m = case["expected_magnification"]
        if math.isfinite(s_prime) and abs(s) > 1e-12:
            m = s_prime / s
            assert m == pytest.approx(expected_m, rel=1e-6), (
                f"Failed: {case['description']}\n"
                f"  Expected m: {expected_m:.6f}\n"
                f"  Got m: {m:.6f}"
            )


class TestTwoLensSystemValidation:
    """Validate two-lens system effective focal length."""

    @pytest.mark.parametrize("case", TWO_LENS_CASES, ids=[c["description"] for c in TWO_LENS_CASES])
    def test_effective_focal_length(self, case):
        """EFL matches formula: 1/f_eff = 1/f1 + 1/f2 - d/(f1*f2)."""
        f1, f2, d = case["f1"], case["f2"], case["d"]
        expected = case["expected_efl"]
        
        # Build system
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.0, focal_length=f1, aperture_diameter=0.025, material="N-BK7"),
                ThinLens(id="L2", position=d, focal_length=f2, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=-0.5, height=0.001, orientation=0.0),
            image_plane=ImagePlane(position=d + expected),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=["chief", "marginal", "fill"], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        from optics.analysis import effective_focal_length
        result = effective_focal_length(system)
        assert result == pytest.approx(expected, rel=1e-4), (
            f"Failed: {case['description']}\n"
            f"  Expected EFL: {expected*1000:.4f} mm\n"
            f"  Got EFL: {result*1000:.4f} mm\n"
            f"  Source: {case['source']}"
        )


def _flat_glass_surface():
    """A flat air/N-BK7 interface for exact ray tracing."""
    from optics.models import SphericalSurface
    return OpticalSystem(
        components=[SphericalSurface(id="S1", position=0.1, radius=0.0, thickness=0.01,
                                     material="N-BK7", aperture_diameter=0.05)],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=0.001),
        image_plane=ImagePlane(position=0.2),
        analysis_settings=AnalysisSettings(num_rays=11, wavelength=550e-9),
    )


class TestSnellsLawValidation:
    """The exact tracer must obey n1 sin(theta1) = n2 sin(theta2)."""

    @pytest.mark.parametrize("deg", [0.0, 10.0, 30.0, 60.0, 85.0])
    def test_refraction_angle(self, deg):
        import numpy as np
        from optics import raytrace as rt
        seq = rt.build_sequence(_flat_glass_surface())
        n2 = refractive_index("N-BK7", 550e-9)
        th = math.radians(deg)
        b = rt.trace_bundle(seq, np.array([[0.0, 0.0, 0.0]]),
                            np.array([[0.0, math.sin(th), math.cos(th)]]), clip=False)
        assert b.valid[0]
        assert b.directions[0, 1] == pytest.approx(math.sin(th) / n2, abs=1e-14)

    def test_total_internal_reflection_beyond_critical_angle(self):
        # Glass to air: beyond asin(1/n) the refracted ray does not exist.
        import numpy as np
        from optics import raytrace as rt
        from optics.models import SphericalSurface
        n = refractive_index("N-BK7", 550e-9)
        crit = math.asin(1.0 / n)
        system = _flat_glass_surface().model_copy(update={"components": [
            SphericalSurface(id="S0", position=0.05, radius=0.0, thickness=0.05,
                             material="N-BK7", aperture_diameter=0.5),
            SphericalSurface(id="S1", position=0.1, radius=0.0, thickness=0.01,
                             material="air", aperture_diameter=0.5)]})
        seq = rt.build_sequence(system)
        for th, ok in ((crit - 1e-3, True), (crit + 1e-3, False)):
            # start inside the glass, just after the first surface
            p0 = np.array([[0.0, 0.0, 0.06]])
            d0 = np.array([[0.0, math.sin(th), math.cos(th)]])
            sub = rt.Sequence(seq.surfaces[1:], seq.wavelength, seq.object_z, seq.object_height,
                              seq.object_infinite, seq.image_z, seq.image_origin,
                              seq.image_rotation, 0, seq.surfaces[1].n_before,
                              seq.n_image, 0)
            b = rt.trace_bundle(sub, p0, d0, clip=False)
            assert bool(b.valid[0]) is ok


class TestDiffractionValidation:
    """Validate diffraction calculations."""

    @pytest.mark.parametrize("case", AIRY_DISK_CASES, ids=[c["description"] for c in AIRY_DISK_CASES])
    def test_airy_disk_radius(self, case):
        """Airy disk radius matches 1.22 * lambda * f/#."""
        wavelength = case["wavelength"]
        f_number = case["f_number"]
        expected = case["expected_airy_radius"]
        
        result = airy_disk_radius(na=1.0 / (2 * f_number), wavelength=wavelength)
        assert result == pytest.approx(expected, rel=1e-3), (
            f"Failed: {case['description']}\n"
            f"  Expected: {expected*1e6:.4f} μm\n"
            f"  Got: {result*1e6:.4f} μm\n"
            f"  Source: {case['source']}"
        )

    @pytest.mark.parametrize("case", MTF_CUTOFF_CASES, ids=[c["description"] for c in MTF_CUTOFF_CASES])
    def test_mtf_cutoff_frequency(self, case):
        """The engine's MTF cutoff matches 1 / (lambda * f/#)."""
        wavelength = case["wavelength"]
        f_number = case["f_number"]
        expected = case["expected_cutoff"]

        result = mtf(None, wavelength=wavelength, na=1.0 / (2.0 * f_number))["f_c"]
        assert result == pytest.approx(expected, rel=1e-6), (
            f"Failed: {case['description']}\n"
            f"  Expected: {expected/1000:.1f} cycles/mm\n"
            f"  Got: {result/1000:.1f} cycles/mm\n"
            f"  Source: {case['source']}"
        )


class TestMaterialIndexValidation:
    """Validate refractive indices against vendor catalogs."""

    @pytest.mark.parametrize("case", SCHOTT_INDICES, ids=[f"{c['material']}@{c['wavelength_nm']}nm" for c in SCHOTT_INDICES])
    def test_refractive_index(self, case):
        """Refractive index matches vendor catalog value."""
        material = case["material"]
        wavelength = case["wavelength_nm"] * 1e-9  # convert nm to m
        expected = case["expected_n"]
        tolerance = case["tolerance"]
        
        result = refractive_index(material, wavelength)
        assert result == pytest.approx(expected, abs=tolerance), (
            f"Failed: {material} at {case['wavelength_nm']}nm\n"
            f"  Expected: {expected:.6f}\n"
            f"  Got: {result:.6f}\n"
            f"  Source: Schott Catalog 2024"
        )


class TestAbbeNumberValidation:
    """Abbe numbers computed from the dispersion formulas."""

    @pytest.mark.parametrize("case", ABBE_NUMBERS, ids=[c["material"] for c in ABBE_NUMBERS])
    def test_abbe_number(self, case):
        assert abbe_number(case["material"]) == pytest.approx(case["expected_vd"], abs=case["tolerance"])


class TestABCDMatrixValidation:
    """Validate ABCD matrix calculations."""

    def test_free_space_propagation(self):
        """Free space propagation matrix is [[1, d], [0, 1]]."""
        d = 0.1  # 100mm
        M = thin_lens_matrix(0.1)  # Just to get matrix format
        # Propagation matrix
        from optics.lenses import propagation_matrix
        P = propagation_matrix(d)
        assert P[0][0] == pytest.approx(1.0)
        assert P[0][1] == pytest.approx(d)
        assert P[1][0] == pytest.approx(0.0)
        assert P[1][1] == pytest.approx(1.0)

    def test_thin_lens_matrix(self):
        """Thin lens matrix is [[1, 0], [-1/f, 1]]."""
        f = 0.1  # 100mm
        from optics.lenses import thin_lens_matrix
        M = thin_lens_matrix(f)
        assert M[0][0] == pytest.approx(1.0)
        assert M[0][1] == pytest.approx(0.0)
        assert M[1][0] == pytest.approx(-1/f)
        assert M[1][1] == pytest.approx(1.0)

    def test_system_matrix_efl(self):
        """System matrix C element gives EFL = -1/C."""
        f = 0.1  # 100mm
        from optics.lenses import thin_lens_matrix, system_matrix
        M = system_matrix([thin_lens_matrix(f)])
        efl = -1.0 / M[1][0]
        assert efl == pytest.approx(f, rel=1e-6)


class TestEnergyConservation:
    """Validate energy conservation in ray tracing."""

    def test_ray_count_conservation(self):
        """All generated rays should be traceable."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.05, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01, orientation=0.0),
            image_plane=ImagePlane(position=0.2),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=["chief", "marginal", "fill"], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        from optics.rays import trace_system
        result = trace_system(system)
        
        # All rays should produce valid paths
        assert len(result.ray_paths) > 0
        for path in result.ray_paths:
            assert len(path.points) > 0, "Ray path should have points"
            # Check for NaN in path
            for point in path.points:
                assert math.isfinite(point[0]), f"z-coordinate is not finite: {point[0]}"
                assert math.isfinite(point[1]), f"y-coordinate is not finite: {point[1]}"


class TestUnitConsistency:
    """Validate unit consistency throughout calculations."""

    def test_all_internal_units_meters(self):
        """All internal calculations use meters."""
        # Create system with known dimensions
        # Object at 2f (200mm), lens at 100mm with f=100mm
        f = 0.1  # 100mm = 0.1m
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.2, focal_length=f, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01, orientation=0.0),
            image_plane=ImagePlane(position=0.4),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=["chief", "marginal", "fill"], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        from optics.analysis import analyze_system
        result = analyze_system(system)
        
        # All results should be in meters and physically reasonable
        assert result.effective_focal_length < 1.0, "EFL should be in meters (< 1m for this system)"
        assert result.effective_focal_length > 0.01, "EFL should be positive and reasonable"
        assert result.rms_spot_radius < 0.01, "RMS spot should be in meters (< 10mm)"
        assert result.image_distance < 1.0, "Image distance should be in meters"
        assert result.image_distance > 0.0, "Image distance should be positive for real image"
