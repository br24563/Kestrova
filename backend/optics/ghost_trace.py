"""
Ghost images of the real prescription (double reflections), traced with
the exact sequential tracer: any surface shape, tilts and decenters, clear
apertures and the surfaces' own coatings.

A ghost (i, j), i after j, follows the system to surface i, reflects there,
travels back through the surfaces between, reflects at j and continues
through the rest of the system to the image plane. For each ghost and
field this reports:
- the fraction of the beam that reaches the image;
- its power relative to the beam: the mean over the arriving rays of the
  unpolarized reflectances R_i R_j at their angles (Fresnel at bare
  surfaces, the thin-film stack where coated). Transmission losses along
  the path are left out;
- the ghost spot's RMS radius and centroid at the image plane;
- where the ghost focuses: the minimum-RMS plane, measured from the image
  plane along the light;
- its irradiance relative to the image: power x (r_image / r_ghost)^2,
  with the image's RMS radius floored at the Airy radius.

Systems with ideal (paraxial) lenses have no surfaces to reflect from and
are refused; mirrors are not ghost surfaces (they reflect the main beam).
"""

from __future__ import annotations

import dataclasses
import math
from typing import Optional

import numpy as np

from . import raytrace as rt
from .coatings.transfer_matrix import reflection_transmission
from .fields import gaussian_pupil, resolve_fields
from .models import OpticalSystem
from .polarization_trace import _layers, _surface_normals


def reflectance(
    n1: float, n2: float, cos_i, wavelength: float, coating=None, reverse: bool = False
) -> np.ndarray:
    """Unpolarized power reflectance from medium n1 at a surface into n2;
    ``reverse`` when the light meets the coating from the side the main beam
    leaves it."""
    cos_i = np.clip(np.abs(np.asarray(cos_i, dtype=float)), 0.0, 1.0)
    if not coating or not coating.get("layers"):
        sin2_t = (n1 / n2) ** 2 * (1 - cos_i**2)
        cos_t = np.sqrt(np.clip(1 - sin2_t, 0.0, None))
        rs = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)) ** 2
        rp = ((n2 * cos_i - n1 * cos_t) / (n2 * cos_i + n1 * cos_t)) ** 2
        return np.where(sin2_t >= 1, 1.0, 0.5 * (rs + rp))
    layers = _layers(coating, wavelength)
    if reverse:
        # the stack is listed in the main beam's direction
        layers = layers[::-1]
    out = []
    for c in cos_i.ravel():
        a = math.acos(min(1.0, float(c)))
        Rs = reflection_transmission(layers, wavelength * 1e9, n1, n2, a, "s")[0]
        Rp = reflection_transmission(layers, wavelength * 1e9, n1, n2, a, "p")[0]
        out.append(0.5 * (Rs + Rp))
    return np.array(out).reshape(cos_i.shape)


def _ghost_sequence(seq, i: int, j: int):
    """The sequence of ghost (i, j): reflect at surface i, back to j,
    reflect, then forward to the image."""
    S = seq.surfaces
    si, sj = S[i], S[j]
    back = [
        dataclasses.replace(s, n_before=s.n_after, n_after=s.n_before)
        for s in reversed(S[j + 1 : i])
    ]
    surfaces = (
        list(S[:i])
        + [
            dataclasses.replace(
                si, kind="reflect", n_before=si.n_before, n_after=si.n_before
            )
        ]
        + back
        + [
            dataclasses.replace(
                sj, kind="reflect", n_before=sj.n_after, n_after=sj.n_after
            )
        ]
        + list(S[j + 1 :])
    )
    # a new sequence: drop the caches of the original
    return dataclasses.replace(seq, surfaces=surfaces, _fast_pack=None, _stop_sub=None)


def _cos_at(seq, pts, k: int):
    """|cos| of incidence of each ray at surface k of a sequence."""
    d = pts[:, k + 1] - pts[:, k]
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    n = _surface_normals(seq.surfaces[k], pts[:, k + 1])
    return np.abs(np.sum(d * n, axis=1))


def _spot(P, D, ok):
    """(centroid x, y, RMS radius, minimum-RMS focus shift along the light)."""
    x, y = P[ok, 0], P[ok, 1]
    cx, cy = x.mean(), y.mean()
    rms = math.sqrt(np.mean((x - cx) ** 2 + (y - cy) ** 2))
    sx = D[ok, 0] / D[ok, 2]
    sy = D[ok, 1] / D[ok, 2]
    sx, sy = sx - sx.mean(), sy - sy.mean()
    den = np.sum(sx * sx + sy * sy)
    dz = -np.sum((x - cx) * sx + (y - cy) * sy) / den if den > 0 else 0.0
    return cx, cy, rms, float(dz * np.sign(np.median(D[ok, 2])))


def ghost_analysis(
    system: OpticalSystem,
    field: Optional[int] = 0,
    wavelength: Optional[float] = None,
    rings: int = 6,
    top: Optional[int] = None,
) -> dict:
    """Every double-reflection ghost at one field, brightest first."""
    wl = wavelength or system.analysis_settings.wavelength
    tracing, fields = resolve_fields(system)
    k = len(fields) - 1 if field is None else field
    if not 0 <= k < len(fields):
        raise ValueError(
            f"Field {k} does not exist (the field table has {len(fields)})"
        )
    f = fields[k]
    seq = rt.build_sequence(tracing, wl)
    if any(s.kind == "ideal" for s in seq.surfaces):
        raise ValueError("Ghost analysis needs real surfaces (no paraxial lenses)")
    fo = rt.first_order(tracing, seq=seq)
    px, py, _ = gaussian_pupil(rings)
    p0, d0, _ = rt.aim_rays(seq, fo, f.hx, f.hy, px, py)

    def at_image(b, s):
        P, D = rt._to_local(s.image_origin, s.image_rotation, b.image, b.directions)
        return P, D

    main = rt.trace_bundle(seq, p0, d0)
    Pm, Dm = at_image(main, seq)
    _, _, r_main, _ = _spot(Pm, Dm, main.valid) if main.valid.any() else (0, 0, 0, 0)
    na = max(abs(fo.na_image), 1e-12)
    r_main = max(r_main, 0.61 * wl / na)

    refract = [n for n, s in enumerate(seq.surfaces) if s.kind == "refract"]
    ghosts: list[dict] = []
    for a, i in enumerate(refract):
        for j in refract[:a]:
            gs = _ghost_sequence(seq, i, j)
            b = rt.trace_bundle(gs, p0, d0)
            ok = b.valid
            entry = {
                "surfaces": [i, j],
                "labels": [seq.surfaces[i].label, seq.surfaces[j].label],
            }
            if not ok.any():
                ghosts.append(
                    {
                        **entry,
                        "fraction": 0.0,
                        "power": 0.0,
                        "rms_radius": None,
                        "centroid": None,
                        "focus_shift": None,
                        "relative_irradiance": 0.0,
                    }
                )
                continue
            ci = _cos_at(gs, b.points, i)
            cj = _cos_at(gs, b.points, i + 1 + len(range(j + 1, i)))
            si, sj = seq.surfaces[i], seq.surfaces[j]
            Ri = reflectance(si.n_before, si.n_after, ci[ok], wl, si.coating)
            Rj = reflectance(sj.n_after, sj.n_before, cj[ok], wl, sj.coating, True)
            frac = float(ok.mean())
            power = float(np.mean(Ri * Rj)) * frac
            P, D = at_image(b, gs)
            cx, cy, rms, dz = _spot(P, D, ok)
            rel = power * (r_main / max(rms, r_main)) ** 2
            ghosts.append(
                {
                    **entry,
                    "fraction": frac,
                    "power": power,
                    "rms_radius": rms,
                    "centroid": [cx, cy],
                    "focus_shift": dz,
                    "relative_irradiance": rel,
                }
            )
    ghosts.sort(key=lambda g: float(g["relative_irradiance"]), reverse=True)
    return {
        "field": f.index,
        "wavelength": wl,
        "image_rms_radius": r_main,
        "ghosts": ghosts[:top] if top else ghosts,
    }
