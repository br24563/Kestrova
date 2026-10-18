"""
Seidel (third-order) aberration analysis.

The five monochromatic Seidel sums S_I..S_V and the two chromatic sums
C_L, C_T are computed surface by surface from the paraxial marginal and
chief rays (Welford, *Aberrations of Optical Systems*, ch. 8; see
:func:`optics.raytrace.seidel_sums`). They are converted to image-space
aberrations at full aperture and full field:

    - spherical aberration: transverse (marginal ray height in the paraxial
      image plane) and longitudinal (shift of the marginal focus)
    - tangential coma
    - astigmatism (tangential minus sagittal focus) and field curvature
      (medial focus (t + s)/2 relative to the paraxial image; the Petzval
      surface is reported separately)
    - distortion (fraction of the paraxial image height)

The same quantities are also measured exactly with real rays (``"real"``
key), so the third-order prediction and the actual system can be
compared. Third-order values are accurate when apertures and fields are
small; the real values hold everywhere.

Longitudinal values are along the axis in the direction of travel,
relative to the paraxial image. All values are in SI units (meters).
"""

import math

import numpy as np

from .models import OpticalSystem, ImagePlane
from . import raytrace as rt


def _at_paraxial_image(system: OpticalSystem, fo: rt.FirstOrder) -> OpticalSystem:
    return system.model_copy(update={"image_plane": ImagePlane(position=fo.image_z)})


def _third_order(system: OpticalSystem):
    sums = rt.seidel_sums(system)
    fo = rt.first_order(system)
    return sums, fo, rt.third_order_aberrations(sums, fo)


def _real_measures(system: OpticalSystem, fo: rt.FirstOrder) -> dict:
    """Exact real-ray measures at the paraxial image plane."""
    s = _at_paraxial_image(system, fo)
    seq = rt.build_sequence(s)
    fo2 = rt.first_order(s, seq=seq)
    o, R = seq.image_origin, seq.image_rotation
    d = seq.image_direction

    def local(b):
        return rt._to_local(o, R, b.image, b.directions)

    out = {}
    b, _, _ = rt.trace_field_rays(
        s, 0, 0, np.array([0.0, 0.0]), np.array([0.0, 1.0]), seq=seq, fo=fo2, clip=False
    )
    P, D = local(b)
    if b.valid.all():
        out["transverse_spherical"] = float(P[1, 1] - P[0, 1])
        slope = D[1, 1] / D[1, 2]
        out["longitudinal_spherical"] = float(-P[1, 1] / slope * d) if slope else 0.0
    if system.object.height:
        b, _, _ = rt.trace_field_rays(
            s,
            0,
            1,
            np.array([0.0, 0.0, 0.0]),
            np.array([0.0, 1.0, -1.0]),
            seq=seq,
            fo=fo2,
            clip=False,
        )
        P, _ = local(b)
        if b.valid.all():
            out["tangential_coma"] = float((P[1, 1] + P[2, 1]) / 2.0 - P[0, 1])
            hp = fo2.image_height
            out["distortion"] = float((P[0, 1] - hp) / hp) if hp else 0.0
        try:
            zt, zs = rt.real_field_foci(s, 1.0, delta=1e-3, seq=seq, fo=fo2)
            out["tangential_focus"] = float(zt * d)
            out["sagittal_focus"] = float(zs * d)
            out["astigmatism"] = float((zt - zs) * d)
        except ValueError:
            pass
    return out


def spherical_aberration(system: OpticalSystem) -> dict:
    """Third-order spherical aberration at full aperture:
    {"longitudinal": m, "transverse": m}."""
    _, _, t3 = _third_order(system)
    return {
        "longitudinal": t3["longitudinal_spherical"],
        "transverse": t3["transverse_spherical"],
    }


def coma(system: OpticalSystem) -> float:
    """Third-order tangential coma (meters) at full aperture and field."""
    _, _, t3 = _third_order(system)
    return t3["tangential_coma"]


def astigmatism_and_field_curvature(system: OpticalSystem) -> dict:
    """
    Third-order astigmatism and field curvature at full field.

    Returns:
        "astigmatism": tangential minus sagittal focus (m)
        "field_curvature": medial focus (t+s)/2 minus paraxial image (m)
        "tangential_focus", "sagittal_focus": positions relative to the
            paraxial image (m)
        "petzval": Petzval surface position relative to the paraxial image (m)
    """
    _, _, t3 = _third_order(system)
    zt = t3["tangential_field_curvature"]
    zs = t3["sagittal_field_curvature"]
    return {
        "astigmatism": zt - zs,
        "field_curvature": (zt + zs) / 2.0,
        "tangential_focus": zt,
        "sagittal_focus": zs,
        "petzval": t3["petzval_field_curvature"],
    }


def distortion(system: OpticalSystem) -> float:
    """Third-order distortion as a fraction of the paraxial image height
    (positive = pincushion, negative = barrel)."""
    _, _, t3 = _third_order(system)
    return t3["fractional_distortion"]


def seidel_analysis(system: OpticalSystem) -> dict:
    """
    Full third-order analysis with the Seidel sums, the per-surface
    contributions, the wavefront coefficients and exact real-ray measures.
    """
    sums, fo, t3 = _third_order(system)
    zt = t3["tangential_field_curvature"]
    zs = t3["sagittal_field_curvature"]
    return {
        "spherical_aberration": {
            "longitudinal": t3["longitudinal_spherical"],
            "transverse": t3["transverse_spherical"],
        },
        "coma": t3["tangential_coma"],
        "astigmatism": zt - zs,
        "field_curvature": (zt + zs) / 2.0,
        "tangential_focus": zt,  # relative to the paraxial image
        "sagittal_focus": zs,
        "petzval_field_curvature": t3["petzval_field_curvature"],
        "distortion": t3["fractional_distortion"],
        "longitudinal_color": t3["longitudinal_color"],
        "lateral_color": t3["lateral_color"],
        "paraxial_image_position": fo.image_z,
        "paraxial_image_height": fo.image_height,
        "seidel_sums": {
            "S1": sums.S1,
            "S2": sums.S2,
            "S3": sums.S3,
            "S4": sums.S4,
            "S5": sums.S5,
            "CL": sums.CL,
            "CT": sums.CT,
        },
        "wavefront_coefficients": {
            "W040": sums.S1 / 8.0,
            "W131": sums.S2 / 2.0,
            "W222": sums.S3 / 2.0,
            "W220": (sums.S3 + sums.S4) / 4.0,
            "W311": sums.S5 / 2.0,
        },
        "per_surface": sums.per_surface,
        "unsupported_surfaces": sums.unsupported,
        "real": _real_measures(system, fo),
        "wavelength": fo.wavelength,
    }
