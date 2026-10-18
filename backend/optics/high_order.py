"""
High-order (exact) aberration diagnostics from real rays.

    - Ray fans: transverse ray error vs pupil coordinate, tangential
      (py, error in y) and sagittal (px, errors in x and y), relative to the
      chief ray in the image plane.
    - OPD map over the 2D pupil (exit-pupil reference sphere).
    - Field curves: real tangential and sagittal focus positions from
      differential rays about the chief ray, and real distortion.
    - Through-focus MTF from the actual pupil function at each focus.
    - Zernike decomposition of the wavefront.

All calculations use :mod:`optics.raytrace` and :mod:`optics.pupil`.
Values are in SI units (meters) unless noted.
"""

import math
from typing import Optional

import numpy as np

from .models import OpticalSystem, ImagePlane
from .zernike import zernike_names
from . import raytrace as rt
from . import pupil as pp
from .wavefront import zernike_decompose


def _local_image(seq, b):
    return rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)[0]


def ray_fan(
    system: OpticalSystem, num_rays: int = 21, field_fraction: float = 1.0
) -> dict:
    """
    Tangential and sagittal ray fans at the system image plane.

    Returns:
        "pupil_x": normalised pupil coordinates (-1..1)
        "transverse_t": tangential fan, y error vs py (meters)
        "transverse_s": sagittal fan, x error vs px (meters)
        "transverse_s_y": sagittal fan, y error vs px (meters)
        "valid_t", "valid_s": rays that passed the apertures
        "chief_ray_height": chief-ray y in the image plane
        "paraxial_image_height": paraxial image height of this field
    """
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    p = np.linspace(-1.0, 1.0, num_rays)
    z = np.zeros_like(p)
    bt, _, _ = rt.trace_field_rays(
        system,
        0.0,
        field_fraction,
        np.concatenate([[0.0], z]),
        np.concatenate([[0.0], p]),
        seq=seq,
        fo=fo,
    )
    bs, _, _ = rt.trace_field_rays(
        system,
        0.0,
        field_fraction,
        np.concatenate([[0.0], p]),
        np.concatenate([[0.0], z]),
        seq=seq,
        fo=fo,
    )
    Pt, Ps = _local_image(seq, bt), _local_image(seq, bs)
    chief = Pt[0]
    et = np.where(bt.valid[1:], Pt[1:, 1] - chief[1], np.nan)
    es = np.where(bs.valid[1:], Ps[1:, 0] - chief[0], np.nan)
    esy = np.where(bs.valid[1:], Ps[1:, 1] - chief[1], np.nan)
    return {
        "pupil_x": p.tolist(),
        "transverse_t": [None if not np.isfinite(v) else float(v) for v in et],
        "transverse_s": [None if not np.isfinite(v) else float(v) for v in es],
        "transverse_s_y": [None if not np.isfinite(v) else float(v) for v in esy],
        "valid_t": bt.valid[1:].tolist(),
        "valid_s": bs.valid[1:].tolist(),
        "chief_ray_height": float(chief[1]),
        "paraxial_image_height": fo.image_height * field_fraction,
        "field_fraction": field_fraction,
    }


def opd_map(
    system: OpticalSystem, num_rays: int = 21, field_fraction: float = 1.0
) -> dict:
    """OPD over the 2D pupil (NaN entries returned as None)."""
    g = pp.wavefront_grid(system, field_fraction, num_rays)
    W = np.where(g.mask, g.W, np.nan)
    return {
        "pupil_x": g.px[0].tolist(),
        "pupil_y": g.py[:, 0].tolist(),
        "opd": [[None if not np.isfinite(v) else float(v) for v in row] for row in W],
        "opd_rms": g.rms,
        "opd_peak_to_valley": g.peak_to_valley,
        "strehl_ratio": pp.strehl_ratio(g),
        "field_fraction": field_fraction,
    }


def opd_fan(
    system: OpticalSystem,
    num_rays: int = 21,
    field_fraction: float = 1.0,
    grid: int = 33,
) -> dict:
    """
    Tangential (py) and sagittal (px) cuts through the OPD at the system
    image plane (meters, None where vignetted), with the RMS, peak-to-valley
    and Strehl ratio of the full 2D pupil sampled on a ``grid`` x ``grid``
    mesh.
    """
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    p = np.linspace(-1.0, 1.0, num_rays)
    z = np.zeros_like(p)
    wt, okt, _ = rt.opd(system, 0.0, field_fraction, z, p, seq=seq, fo=fo)
    ws, oks, _ = rt.opd(system, 0.0, field_fraction, p, z, seq=seq, fo=fo)
    g = pp.wavefront_grid(system, field_fraction, grid)

    def clean(w, ok):
        return [float(v) if k and np.isfinite(v) else None for v, k in zip(w, ok)]

    return {
        "pupil": p.tolist(),
        "opd_t": clean(wt, okt),
        "opd_s": clean(ws, oks),
        "opd_rms": g.rms,
        "opd_peak_to_valley": g.peak_to_valley,
        "strehl_ratio": pp.strehl_ratio(g),
        "wavelength": g.wavelength,
        "field_fraction": field_fraction,
    }


def field_extent(system: OpticalSystem) -> dict:
    """The full field the fractions refer to: a half-angle in degrees for an
    object at infinity, otherwise the object height in meters."""
    fo = rt.first_order(system)
    if fo.object_infinite:
        return {"field_max": math.degrees(fo.field_angle), "field_unit": "deg"}
    return {"field_max": system.object.height, "field_unit": "m"}


def require_finite_image(system: OpticalSystem) -> None:
    """Raise ValueError when the paraxial image is at infinity (afocal image
    space), where image-plane ray errors and focus positions are undefined."""
    if not math.isfinite(rt.first_order(system).image_z):
        raise ValueError(
            "Image is at infinity (afocal image space): transverse ray "
            "errors and focus positions are undefined."
        )


def field_curves(system: OpticalSystem, num_fields: int = 11) -> dict:
    """
    Real tangential/sagittal foci and distortion versus field.

    Foci are along the axis from the paraxial image plane (positive = further
    in the direction of travel); distortion is the real chief-ray height
    relative to the paraxial image height, as a fraction. The Petzval
    surface is the third-order one from the Petzval sum.
    """
    seq0 = rt.build_sequence(system)
    fo0 = rt.first_order(system, seq=seq0)
    s = system.model_copy(update={"image_plane": ImagePlane(position=fo0.image_z)})
    seq = rt.build_sequence(s)
    fo = rt.first_order(s, seq=seq)
    d = seq.image_direction
    fracs = np.linspace(0.0, 1.0, num_fields)
    # Petzval surface (third order: depends only on the Petzval sum S_IV)
    try:
        t3 = rt.third_order_aberrations(rt.seidel_sums(s), fo)
        petz = [t3["petzval_field_curvature"] * ff * ff for ff in fracs]
    except ValueError:
        petz = [None] * len(fracs)
    tf, sf, ast, dist, med = [], [], [], [], []
    for ff in fracs:
        zt, zs = rt.real_field_foci(s, float(ff), delta=1e-3, seq=seq, fo=fo)
        tf.append(zt * d)
        sf.append(zs * d)
        ast.append((zt - zs) * d)
        med.append((zt + zs) / 2.0 * d)
        if ff == 0.0 or not fo.image_height:
            dist.append(0.0)
            continue
        b, _, _ = rt.trace_field_rays(
            s,
            0.0,
            float(ff),
            np.array([0.0]),
            np.array([0.0]),
            seq=seq,
            fo=fo,
            clip=False,
        )
        yc = _local_image(seq, b)[0, 1]
        hp = fo.image_height * ff
        dist.append(float((yc - hp) / hp))
    return {
        "field_fractions": fracs.tolist(),
        "tangential_focus": tf,
        "sagittal_focus": sf,
        "astigmatism": ast,
        "medial_focus": med,
        "petzval": petz,
        "distortion": dist,
    }


def through_focus_mtf(
    system: OpticalSystem,
    defocus_range: tuple = (-50e-6, 50e-6),
    num_points: int = 21,
    spatial_frequency: float = 50.0,
    field_fraction: float = 0.0,
    grid: int = 48,
) -> dict:
    """
    Diffraction MTF (tangential) at one spatial frequency (cycles/mm) versus
    image-plane position, from the pupil function at each focus.
    """
    nu = spatial_frequency * 1e3
    dz = np.linspace(defocus_range[0], defocus_range[1], num_points)
    vals = np.array(
        [
            pp.mtf_at(
                pp.mtf(
                    pp.wavefront_grid(system, field_fraction, grid, defocus=float(z))
                ),
                nu,
                "tangential",
            )
            for z in dz
        ]
    )
    i = int(np.argmax(vals))
    above = dz[vals >= 0.5 * vals[i]]
    return {
        "defocus": dz.tolist(),
        "mtf": vals.tolist(),
        "best_focus": float(dz[i]),
        "best_mtf": float(vals[i]),
        "depth_of_focus": float(above[-1] - above[0]) if above.size >= 2 else 0.0,
        "spatial_frequency_cyc_per_mm": spatial_frequency,
    }


def zernike_from_rays(
    system: OpticalSystem,
    num_rays: int = 51,
    num_zernike: int = 16,
    field_fraction: float = 1.0,
) -> dict:
    """Noll Zernike fit of the real-ray wavefront."""
    z = zernike_decompose(system, num_rays, num_zernike, field_fraction)
    return {
        "coefficients": z.coefficients,
        "zernike_names": zernike_names(num_zernike),
        "rms_wavefront": z.rms_wavefront,
        "peak_to_valley": z.peak_to_valley,
        "strehl_ratio": z.strehl_ratio,
        "fit_residual_rms": z.fit_residual_rms,
        "wavefront_map": z.wavefront_map,
        "pupil_x": z.pupil_x,
        "pupil_y": z.pupil_y,
    }


def high_order_analysis(
    system: OpticalSystem,
    num_rays_fan: int = 21,
    num_rays_opd: int = 21,
    num_fields: int = 11,
    num_zernike: int = 16,
) -> dict:
    """Ray fans, OPD map, field curves and Zernike fit at full field."""
    fan = ray_fan(system, num_rays_fan, 1.0)
    opd = opd_map(system, num_rays_opd, 1.0)
    curves = field_curves(system, num_fields)
    zern = zernike_from_rays(system, num_rays_opd, num_zernike, 1.0)
    wl = system.analysis_settings.wavelength
    return {
        "ray_fan": fan,
        "opd_map": opd,
        "field_curves": curves,
        "zernike": zern,
        "summary": {
            "rms_wavefront_waves": zern["rms_wavefront"] / wl,
            "peak_to_valley_waves": zern["peak_to_valley"] / wl,
            "strehl_ratio": zern["strehl_ratio"],
            "is_diffraction_limited": zern["strehl_ratio"] >= 0.8,
            "max_distortion_percent": max(abs(v) for v in curves["distortion"]) * 100,
            "max_astigmatism_um": max(abs(v) for v in curves["astigmatism"]) * 1e6,
            "chief_ray_height_um": fan["chief_ray_height"] * 1e6,
            "paraxial_image_height_um": fan["paraxial_image_height"] * 1e6,
        },
    }
