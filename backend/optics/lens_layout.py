"""
Layout of a prescription for drawing: element outlines and real rays.

- ``elements``: the outline of each glass element and mirror in its
  meridional section, as (z, r) points in metres from the axis outward
  over the front, along the edge and back to the axis over the rear (the
  same solids as the STEP export, so the drawing and the CAD agree);
- ``rays``: exact rays per field through the real system, each a list of
  (x, y, z) points: the start, every surface and the image plane. A
  "fan" pupil traces the meridional (y) fan for a 2D section; a "ring"
  pupil adds the marginal ring for a 3D view. Vignetted rays are dropped;
- ``stop`` and ``image``: the aperture stop (z, semi-diameter) and the
  image plane (z, half height covering the rays).

Surfaces that the outlines cannot show (tilted or non-symmetric ones) are
listed in ``warnings``; their rays are still traced.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .lens_data import LensData, configured, resolve, to_system

_KM = 1e-3  # outlines come in mm


def _sampled_outline(body) -> list[list[float]]:
    """The body's outline as (z, r) points in metres (optical faces sampled)."""
    pts: list[list[float]] = []
    for face in body.faces:
        if face.kind == "surface":
            r0, r1 = face.a[1], face.b[1]
            for t in np.linspace(0.0, 1.0, 33):
                r = r0 + (r1 - r0) * t
                pts.append([face.sag(r) * _KM, r * _KM])
        else:
            pts.append([face.a[0] * _KM, face.a[1] * _KM])
            pts.append([face.b[0] * _KM, face.b[1] * _KM])
    out: list[list[float]] = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 1e-12 or abs(p[1] - out[-1][1]) > 1e-12:
            out.append(p)
    return out


def lens_layout(
    lens: LensData,
    configuration: int = 0,
    rays: int = 7,
    pupil: str = "fan",
    wavelength: Optional[float] = None,
) -> dict:
    """Outlines and traced rays of a lens (see the module notes)."""
    from . import raytrace as rt
    from .fields import resolve_fields
    from .io.cad_export import lens_bodies

    if lens.num_configurations > 1:
        lens = configured(lens, configuration)
    lens = resolve(lens)
    system = to_system(lens)
    bodies, warnings = lens_bodies(lens)
    elements = [{"name": b.name, "outline": _sampled_outline(b)} for b in bodies]

    tracing, fields = resolve_fields(system)
    wl = wavelength or system.analysis_settings.wavelength
    seq = rt.build_sequence(tracing, wl)
    fo = rt.first_order(tracing, seq=seq)
    n = max(int(rays), 2)
    if pupil == "ring":
        ang = np.linspace(0.0, 2 * math.pi, 2 * n, endpoint=False)
        px = np.concatenate([np.linspace(0, 0, 1), np.sin(ang)])
        py = np.concatenate([np.zeros(1), np.cos(ang)])
    else:
        py = np.linspace(-1.0, 1.0, n)
        px = np.zeros_like(py)
    out_rays = []
    max_h = 0.0
    for f in fields:
        b, _, _ = rt.trace_field_rays(tracing, f.hx, f.hy, px, py, seq=seq, fo=fo)
        pts = np.asarray(b.points)
        for k in range(len(px)):
            if not b.valid[k]:
                continue
            path = pts[k]
            if not np.all(np.isfinite(path)):
                continue
            out_rays.append(
                {
                    "field": f.index,
                    "pupil": [float(px[k]), float(py[k])],
                    "points": path.tolist(),
                }
            )
            max_h = max(max_h, float(np.hypot(path[-1, 0], path[-1, 1])))
    stop = seq.surfaces[seq.stop_index]
    return {
        "elements": elements,
        "rays": out_rays,
        "fields": len(fields),
        "stop": {"z": float(stop.z), "semi_diameter": float(fo.stop_semi_diameter)},
        "image": {"z": float(system.image_plane.position), "half_height": max_h},
        "warnings": warnings,
    }
