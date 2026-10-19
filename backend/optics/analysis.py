"""
Optical analysis: first-order properties and the real-ray spot.

First-order quantities (focal lengths, magnification, pupils, F-numbers)
come from paraxial ray traces through the full surface sequence in
:mod:`optics.raytrace`, so thick lenses, mirrors and surfaces are handled
exactly to first order. The numerical aperture is taken from the real
marginal ray, and the RMS spot from a grid of real rays across the pupil.

Sign convention:
    - Object distance s: NEGATIVE if the object is to the LEFT of the first
      surface.
    - Image distance s': POSITIVE if the image is beyond the last surface in
      the direction light travels after it.
    - Magnification m: negative = inverted.

All values are in SI base units (meters, radians), evaluated at the system's
analysis wavelength.
"""

import math
from typing import Optional

import numpy as np

from .models import OpticalSystem, AnalysisResult
from . import raytrace as rt


def _wl(system: OpticalSystem) -> float:
    return system.analysis_settings.wavelength


def _fo(system: OpticalSystem) -> rt.FirstOrder:
    return rt.first_order(system, _wl(system))


# ---------------------------------------------------------------------------
# System matrix and focal lengths
# ---------------------------------------------------------------------------


def build_system_matrix(system: OpticalSystem) -> np.ndarray:
    """
    Paraxial transfer matrix [[A, B], [C, D]] from the first surface to the
    last, acting on (y, n*u).

    C = -power, so the effective focal length is -1/C.
    """
    seq = rt.build_sequence(system, _wl(system))
    a = rt.paraxial_trace(seq, 1.0, 0.0)  # (y, nu) = (1, 0)
    b = rt.paraxial_trace(seq, 0.0, 1.0)  # (y, nu) = (0, n0)
    n0 = rt.signed_indices(seq)[0][0]
    return np.array(
        [
            [a.y[-1], b.y[-1] / n0],
            [a.nu_after[-1], b.nu_after[-1] / n0],
        ]
    )


def effective_focal_length(system: OpticalSystem) -> float:
    """Effective focal length (meters); raises ValueError for an afocal system."""
    efl = _fo(system).efl
    if not math.isfinite(efl):
        raise ValueError("System is afocal (infinite effective focal length).")
    return efl


def back_focal_length(system: OpticalSystem) -> float:
    """Distance from the last surface to the rear focal point (meters)."""
    fo = _fo(system)
    if not math.isfinite(fo.bfl):
        raise ValueError("System is afocal: back focal length is undefined.")
    return fo.bfl


def front_focal_length(system: OpticalSystem) -> float:
    """Distance from the front focal point to the first surface (meters)."""
    fo = _fo(system)
    if not math.isfinite(fo.ffl):
        raise ValueError("System is afocal: front focal length is undefined.")
    return fo.ffl


# ---------------------------------------------------------------------------
# Magnification and distances
# ---------------------------------------------------------------------------


def system_magnification(system: OpticalSystem) -> float:
    """Paraxial transverse magnification (0 for an object at infinity)."""
    return _fo(system).magnification


def object_distance(system: OpticalSystem) -> float:
    """Signed distance from the first surface to the object (negative = left)."""
    seq = rt.build_sequence(system, _wl(system))
    return system.object.position - seq.surfaces[0].z


def image_distance(system: OpticalSystem) -> float:
    """Distance from the last surface to the paraxial image, along the
    direction light travels after the last surface."""
    seq = rt.build_sequence(system, _wl(system))
    fo = rt.first_order(system, seq=seq)
    return (fo.image_z - seq.surfaces[-1].z) * seq.image_direction


def working_distance(system: OpticalSystem) -> float:
    """Distance from the last surface to the image plane, along the travel."""
    seq = rt.build_sequence(system, _wl(system))
    return (system.image_plane.position - seq.surfaces[-1].z) * seq.image_direction


# ---------------------------------------------------------------------------
# F-number and numerical aperture
# ---------------------------------------------------------------------------


def system_f_number(system: OpticalSystem) -> float:
    """F-number = EFL / entrance-pupil diameter (the infinite-conjugate F/#)."""
    return _fo(system).f_number


def working_f_number(system: OpticalSystem) -> float:
    """Working F-number 1 / (2 NA') from the real image-space marginal ray."""
    na = system_numerical_aperture(system)
    return 1.0 / (2.0 * na) if na > 0 else math.inf


def _real_marginal_sin(system: OpticalSystem, image_side: bool) -> float:
    seq = rt.build_sequence(system, _wl(system))
    fo = rt.first_order(system, seq=seq)
    b, _, _ = rt.trace_field_rays(
        system, 0.0, 0.0, np.array([0.0]), np.array([1.0]), seq=seq, fo=fo, clip=False
    )
    if not b.valid[0]:
        raise ValueError("The marginal ray cannot be traced")
    if image_side:
        d = b.directions[0]
        axis = seq.image_rotation[:, 2]
    else:
        p0, p1 = b.points[0, 0], b.points[0, 1]
        d = (p1 - p0) / np.linalg.norm(p1 - p0)
        axis = np.array([0.0, 0.0, 1.0])
    cos_u = abs(float(np.dot(d, axis)))
    return math.sqrt(max(0.0, 1.0 - cos_u * cos_u))


def system_numerical_aperture(system: OpticalSystem) -> float:
    """Image-space numerical aperture n' sin U' of the real marginal ray."""
    seq = rt.build_sequence(system, _wl(system))
    return seq.n_image * _real_marginal_sin(system, image_side=True)


def object_numerical_aperture(system: OpticalSystem) -> float:
    """Object-space numerical aperture n sin U (0 for an object at infinity)."""
    seq = rt.build_sequence(system, _wl(system))
    if seq.object_infinite:
        return 0.0
    return seq.n_object * _real_marginal_sin(system, image_side=False)


# ---------------------------------------------------------------------------
# Real-ray spot
# ---------------------------------------------------------------------------


def real_spot(
    system: OpticalSystem,
    field_fraction: float = 1.0,
    grid: int = 15,
    aperture_fraction: float = 1.0,
    wavelength: Optional[float] = None,
):
    """
    Real-ray spot at the image plane for the field point at
    ``field_fraction`` of the object height.

    Returns (points [[x, y], ...] relative to the centroid, rms radius about
    the centroid, centroid (x, y), number of rays traced, number vignetted).

    The points (for plotting) come from a ``grid`` x ``grid`` pupil grid;
    the RMS radius and centroid integrate over the pupil area by Gaussian
    quadrature (Forbes 1988), which a square grid only approximates at the
    pupil rim.
    """
    from .fields import gaussian_pupil

    wl = wavelength if wavelength is not None else _wl(system)
    seq = rt.build_sequence(system, wl)
    fo = rt.first_order(system, seq=seq)
    px, py = rt.pupil_grid(grid)
    px, py = px * aperture_fraction, py * aperture_fraction
    b, _, _ = rt.trace_field_rays(system, 0.0, field_fraction, px, py, seq=seq, fo=fo)
    pl, _ = rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)
    pts = pl[b.valid][:, :2]
    if len(pts) == 0:
        return [], 0.0, (0.0, 0.0), len(px), len(px)
    gx, gy, gw = gaussian_pupil(10)  # independent of the plot grid
    bg, _, _ = rt.trace_field_rays(
        system,
        0.0,
        field_fraction,
        gx * aperture_fraction,
        gy * aperture_fraction,
        seq=seq,
        fo=fo,
    )
    if bg.valid.any():
        gp = rt._to_local(
            seq.image_origin, seq.image_rotation, bg.image, bg.directions
        )[0]
        gp = gp[bg.valid][:, :2]
        w = gw[bg.valid] / gw[bg.valid].sum()
        c = (gp * w[:, None]).sum(axis=0)
        rms = float(np.sqrt(np.sum(w * np.sum((gp - c) ** 2, axis=1))))
    else:
        c = pts.mean(axis=0)
        rms = float(np.sqrt(np.mean(np.sum((pts - c) ** 2, axis=1))))
    rel = pts - c
    return rel.tolist(), rms, (float(c[0]), float(c[1])), len(px), int((~b.valid).sum())


# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------


def analyze_system(
    system: OpticalSystem,
    num_rays: Optional[int] = None,
    aperture_fraction: Optional[float] = None,
) -> AnalysisResult:
    """
    First-order properties plus the real-ray spot at the full object height.

    ``num_rays`` sets the pupil sampling (rays across the pupil diameter;
    default 15).
    """
    if aperture_fraction is None:
        aperture_fraction = system.analysis_settings.aperture_fraction
    grid = num_rays if num_rays and num_rays > 1 else 15
    seq = rt.build_sequence(system, _wl(system))
    fo = rt.first_order(system, seq=seq)

    efl = fo.efl
    points, rms, _, _, _ = real_spot(system, 1.0, grid, aperture_fraction)
    img_dist = (fo.image_z - seq.surfaces[-1].z) * seq.image_direction
    na = system_numerical_aperture(system)
    return AnalysisResult(
        effective_focal_length=efl,
        magnification=fo.magnification,
        image_distance=img_dist,
        object_distance=system.object.position - seq.surfaces[0].z,
        f_number=fo.f_number,
        numerical_aperture=na,
        aperture_diameter=2.0 * fo.entrance_pupil_semi_diameter,
        working_distance=(system.image_plane.position - seq.surfaces[-1].z)
        * seq.image_direction,
        rms_spot_radius=rms,
        spot_points=points,
        is_image_real=img_dist > 0,
        is_image_inverted=(
            fo.magnification < 0
            if not seq.object_infinite
            else fo.image_height * system.object.height < 0
        ),
    )
