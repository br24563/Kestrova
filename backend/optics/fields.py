"""
Field points, wavelength weights and field-by-field analyses.

A system's field table (:class:`~optics.models.FieldPoint`) lists points
in x and y in one of three units, as Code V does:

- ``object_height``: object coordinates (m), for a finite object;
- ``angle``: field angles (rad) for an object at infinity; the incoming
  ray direction has tangents (tan x, tan y);
- ``paraxial_image_height``: the paraxial image point (m); the object
  point is found through the paraxial magnification.

Without a field table the fields are on axis, 0.7 and 1.0 of the
system's object height along y (Code V's default fractions).

The engine traces a field point (hx, hy) as fractions of
``system.object.height``. :func:`resolve_fields` converts the table into
those fractions on a tracing copy of the system whose object height is the
largest field, so every point is traced at its true position whatever the
system's own object height is.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from . import raytrace as rt
from .models import Object, OpticalSystem
from .pupil import polychromatic_mtf, vignetted_pupil

DEFAULT_FRACTIONS = (0.0, 0.7, 1.0)


@dataclass
class ResolvedField:
    index: int
    x: float  # as given, in the field type's units
    y: float
    hx: float  # fractions of the tracing system's object height
    hy: float
    weight: float
    vignetting: tuple  # (vux, vlx, vuy, vly)

    @property
    def azimuth(self) -> float:
        """Direction of the field point in the image, from +y toward +x."""
        return math.atan2(self.hx, self.hy) if (self.hx or self.hy) else 0.0


def field_type(system: OpticalSystem) -> str:
    """The units of the field table (default: angle at infinity, else object height)."""
    if system.field_type is not None:
        return system.field_type
    return "angle" if rt.build_sequence(system).object_infinite else "object_height"


def wavelength_weights(system: OpticalSystem) -> list[float]:
    """Wavelength weights normalised to sum 1 (equal when unset)."""
    w = system.wavelength_weights or [1.0] * len(system.wavelengths)
    total = float(sum(w))
    return [x / total for x in w]


def resolve_fields(system: OpticalSystem) -> tuple[OpticalSystem, list[ResolvedField]]:
    """
    (tracing system, fields): the tracing system is ``system`` with its
    object height set to the largest field (unchanged without a field
    table), and each field's (hx, hy) are fractions of that height.
    """
    if system.fields is None:
        fracs = DEFAULT_FRACTIONS if system.object.height else (0.0,)
        return system, [
            ResolvedField(
                i, 0.0, f * system.object.height, 0.0, f, 1.0, (0.0, 0.0, 0.0, 0.0)
            )
            for i, f in enumerate(fracs)
        ]
    seq = rt.build_sequence(system)
    ftype = field_type(system)
    distance = seq.surfaces[0].z - seq.object_z
    if ftype == "angle" and not seq.object_infinite:
        raise ValueError("Angle fields need an object at infinity; use object heights")
    if ftype == "object_height" and seq.object_infinite:
        raise ValueError("Object-height fields need a finite object; use angles")
    # object-space coordinates of each field point
    if ftype == "object_height":
        obj = [(f.x, f.y) for f in system.fields]
    elif ftype == "angle":
        for f in system.fields:
            if abs(f.x) >= math.pi / 2 or abs(f.y) >= math.pi / 2:
                raise ValueError("Field angles must be below 90 degrees")
        obj = [
            (distance * math.tan(f.x), distance * math.tan(f.y)) for f in system.fields
        ]
    else:
        # paraxial image height = k * object height, k from a unit field
        h_ref = system.object.height or (
            distance * 1e-3 if seq.object_infinite else 1e-3
        )
        ref = system.model_copy(
            update={"object": Object(position=system.object.position, height=h_ref)}
        )
        k = rt.first_order(ref).image_height / h_ref
        if not math.isfinite(k) or k == 0:
            raise ValueError(
                "Paraxial image heights need a finite, non-zero magnification"
            )
        obj = [(f.x / k, f.y / k) for f in system.fields]
    h_max = max(math.hypot(x, y) for x, y in obj)
    if h_max == 0:
        tracing = system
        scale = system.object.height or 1.0
    else:
        tracing = system.model_copy(
            update={"object": Object(position=system.object.position, height=h_max)}
        )
        scale = h_max
    fields = [
        ResolvedField(
            i, f.x, f.y, x / scale, y / scale, f.weight, (f.vux, f.vlx, f.vuy, f.vly)
        )
        for i, (f, (x, y)) in enumerate(zip(system.fields, obj))
    ]
    return tracing, fields


@functools.lru_cache(maxsize=64)
def _gaussian_pupil_cached(rings: int, arms: int) -> tuple:
    x, w = np.polynomial.legendre.leggauss(rings)
    r = np.sqrt((x + 1.0) / 2.0)
    th = (np.arange(arms) + 0.5) * (2 * np.pi / arms)
    R, T = np.meshgrid(r, th, indexing="ij")
    W = np.repeat((w / 2.0)[:, None] / arms, arms, axis=1)
    out = ((R * np.cos(T)).ravel(), (R * np.sin(T)).ravel(), W.ravel())
    for arr in out:
        arr.setflags(write=False)
    return out


def gaussian_pupil(rings: int, arms: Optional[int] = None) -> tuple:
    """
    Gaussian quadrature over the unit pupil (G. W. Forbes, JOSA A 5, 1943,
    1988): ring radii at the Gauss-Legendre nodes in r^2, ``arms`` equally
    spaced azimuths per ring. Returns (px, py, weights) with weights summing
    to 1, so sum(w * f) integrates f over the pupil area exactly for
    polynomials of degree 2 * rings - 1 in r^2.
    """
    return _gaussian_pupil_cached(int(rings), int(arms or max(6, 4 * rings)))


def pupil_samples(rings: int, vignetting: tuple) -> tuple:
    """
    (px, py, weights): the pupil centre (the reference ray, weight 0)
    followed by Gaussian-quadrature samples, all mapped into the field's
    vignetted pupil ellipse (an affine map, so the weights are unchanged).
    """
    gx, gy, gw = gaussian_pupil(rings)
    px = np.concatenate([[0.0], gx])
    py = np.concatenate([[0.0], gy])
    w = np.concatenate([[0.0], gw])
    cx, cy, ax, ay = vignetted_pupil(vignetting)
    return cx + ax * px, cy + ay * py, w


def _image_local(seq, b) -> np.ndarray:
    return rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)[0]


def field_summary(system: OpticalSystem, rings: int = 8) -> dict:
    """
    Per-field real-ray results at the image plane:

    - chief ray position (stop centre, reference wavelength) and paraxial
      image position; distortion = (real - paraxial) / paraxial radially;
    - polychromatic spot: rays sampled by Gaussian quadrature over the
      pupil (each carrying its share of pupil area), each wavelength
      weighted by its weight, RMS radius about the weighted centroid, plus
      each wavelength's own RMS;
    - fraction of the pupil area vignetted (averaged over wavelengths).

    ``weighted_rms_spot`` = sqrt(sum w_f rms_f^2 / sum w_f).
    """
    tracing, fields = resolve_fields(system)
    weights = wavelength_weights(system)
    ref_wl = system.analysis_settings.wavelength
    seq_ref = rt.build_sequence(tracing, ref_wl)
    fo_ref = rt.first_order(tracing, seq=seq_ref)
    rows: list[dict[str, Any]] = []
    for f in fields:
        b, _, _ = rt.trace_field_rays(
            tracing,
            f.hx,
            f.hy,
            np.array([0.0]),
            np.array([0.0]),
            seq=seq_ref,
            fo=fo_ref,
            clip=False,
        )
        chief = _image_local(seq_ref, b)[0] if b.valid[0] else None
        par_h = fo_ref.image_height
        paraxial = (f.hx * par_h, f.hy * par_h) if math.isfinite(par_h) else None
        distortion = None
        if chief is not None and paraxial is not None:
            r_par = math.hypot(*paraxial)
            if r_par > 0:
                distortion = (math.hypot(chief[0], chief[1]) - r_par) / r_par
        px, py, pw = pupil_samples(rings, f.vignetting)
        px, py, pw = px[1:], py[1:], pw[1:]  # the reference ray is not part of the spot
        pts, wts, per_wl, traced, passed = [], [], [], 0.0, 0.0
        for wl, w in zip(system.wavelengths, weights):
            seq = rt.build_sequence(tracing, wl)
            fo = rt.first_order(tracing, seq=seq)
            bw, _, _ = rt.trace_field_rays(tracing, f.hx, f.hy, px, py, seq=seq, fo=fo)
            P = _image_local(seq, bw)[bw.valid][:, :2]
            area = pw[bw.valid]
            traced += 1.0
            passed += float(area.sum())
            if len(P):
                a = area / area.sum()
                c = (P * a[:, None]).sum(axis=0)
                per_wl.append(
                    {
                        "wavelength": wl,
                        "weight": w,
                        "rms_spot": float(
                            np.sqrt(np.sum(a * np.sum((P - c) ** 2, axis=1)))
                        ),
                        "centroid": [float(c[0]), float(c[1])],
                    }
                )
                pts.append(P)
                wts.append(w * a)
            else:
                per_wl.append(
                    {"wavelength": wl, "weight": w, "rms_spot": None, "centroid": None}
                )
        if pts:
            P = np.vstack(pts)
            W = np.concatenate(wts)
            W = W / W.sum()
            c = (P * W[:, None]).sum(axis=0)
            rms = float(np.sqrt(np.sum(W * np.sum((P - c) ** 2, axis=1))))
            centroid = [float(c[0]), float(c[1])]
        else:
            rms, centroid = None, None
        rows.append(
            {
                "index": f.index,
                "x": f.x,
                "y": f.y,
                "weight": f.weight,
                "relative_x": f.hx,
                "relative_y": f.hy,
                "vignetting": list(f.vignetting),
                "chief_ray": (
                    [float(chief[0]), float(chief[1])] if chief is not None else None
                ),
                "paraxial_image": list(paraxial) if paraxial is not None else None,
                "distortion": distortion,
                "rms_spot": rms,
                "centroid": centroid,
                "wavelengths": per_wl,
                "vignetted_fraction": 1.0 - passed / traced if traced else None,
            }
        )
    valid: list[tuple[float, float]] = [
        (float(r["weight"]), float(r["rms_spot"]))
        for r in rows
        if r["rms_spot"] is not None
    ]
    wsum = sum(w for w, _ in valid)
    weighted = math.sqrt(sum(w * r * r for w, r in valid) / wsum) if wsum > 0 else None
    return {
        "field_type": (
            field_type(system) if system.fields is not None else "default_fractions"
        ),
        "fields": rows,
        "wavelength_weights": weights,
        "weighted_rms_spot": weighted,
    }


def field_mtf(
    system: OpticalSystem,
    index: int,
    frequencies: Optional[list] = None,
    grid: int = 64,
) -> dict:
    """
    Polychromatic (wavelength-weighted) diffraction MTF of one field point,
    tangential along the field's image direction and sagittal across it,
    within its vignetted pupil. ``frequencies`` in cycles/mm.
    """
    tracing, fields = resolve_fields(system)
    if not 0 <= index < len(fields):
        raise ValueError(f"Field {index} does not exist ({len(fields)} fields)")
    f = fields[index]
    freqs = None if frequencies is None else np.asarray(frequencies, dtype=float) * 1e3
    res = polychromatic_mtf(
        tracing,
        f.hy,
        wavelengths=list(system.wavelengths),
        weights=wavelength_weights(system),
        n=grid,
        frequencies=freqs,
        field_x=f.hx,
        vignetting=f.vignetting,
        azimuth=f.azimuth,
    )
    return {
        "field": index,
        "frequency_cyc_per_mm": (np.asarray(res["frequency"]) / 1e3).tolist(),
        "tangential": np.asarray(res["tangential"]).tolist(),
        "sagittal": np.asarray(res["sagittal"]).tolist(),
        "cutoff_cyc_per_mm": res["cutoff"] / 1e3,
        "azimuth": f.azimuth,
    }
