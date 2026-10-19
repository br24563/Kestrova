"""
Compiled real-ray trace for the common case (Numba, optional).

:func:`optics.raytrace.trace_bundle` hands a sequence here when every
surface is a sphere or conic (refracting or reflecting), an aperture stop
or a dummy, in any frames (coordinate breaks included). The kernel performs
exactly the operations of the NumPy trace, ray by ray and in parallel:
the stable small root of the conic quadratic, the conic normal, vector
Snell refraction or reflection, clear-aperture clipping and optical path.
Other surfaces (ideal lenses, aspheres, DOEs, ...) use the NumPy trace.

Numba is optional: without it (or with the environment variable
``OPTICS_NO_NUMBA`` set) everything uses the NumPy trace.
"""

from __future__ import annotations

import importlib
import os

from typing import Any

import numpy as np

numba: Any
try:  # pragma: no cover - depends on the environment
    if os.environ.get("OPTICS_NO_NUMBA"):
        raise ImportError("disabled by OPTICS_NO_NUMBA")
    numba = importlib.import_module("numba")

    AVAILABLE = True
except ImportError:  # pragma: no cover
    numba = None
    AVAILABLE = False

_REFRACT, _REFLECT, _PLANE = 0, 1, 2


def supports(seq) -> bool:
    """Whether the compiled kernel can trace this sequence."""
    if not AVAILABLE:
        return False
    from .raytrace import Conicoid

    for s in seq.surfaces:
        if s.kind in ("stop", "dummy"):
            continue
        if s.kind not in ("refract", "reflect") or s.phase is not None:
            return False
        if type(s.shape) is not Conicoid or s.shape.even or s.shape.odd:
            return False
    return True


def _pack(seq):
    packed = getattr(seq, "_fast_pack", None)
    if packed is not None:
        return packed
    M = len(seq.surfaces)
    kind = np.empty(M, dtype=np.int64)
    c = np.zeros(M)
    k = np.zeros(M)
    origin = np.zeros((M, 3))
    rot = np.zeros((M, 3, 3))
    ident = np.zeros(M, dtype=np.bool_)
    semi = np.full(M, -1.0)
    n1 = np.zeros(M)
    n2 = np.zeros(M)
    for j, s in enumerate(seq.surfaces):
        kind[j] = {"refract": _REFRACT, "reflect": _REFLECT}.get(s.kind, _PLANE)
        if kind[j] != _PLANE:
            c[j], k[j] = s.shape.c, s.shape.k
        origin[j] = s.origin
        rot[j] = s.rotation
        ident[j] = bool(np.array_equal(s.rotation, np.eye(3)))
        if s.semi_aperture is not None:
            semi[j] = s.semi_aperture
        n1[j], n2[j] = s.n_before, s.n_after
    packed = (kind, c, k, origin, rot, ident, semi, n1, n2)
    try:
        seq._fast_pack = packed
    except AttributeError:  # pragma: no cover
        pass
    return packed


#: Rays per call above which the parallel kernel is used. Below it the
#: serial kernel avoids thread start-up (about 0.5 ms per call), which
#: dominates small traces such as ray aiming and optimizer merits.
PARALLEL_MIN_RAYS = 4096


def _kernel_impl(
    p0, d0, kind, c, k, origin, rot, ident, semi, n1, n2, n_start, img_o, img_R, clip
):
    N = p0.shape[0]
    M = kind.shape[0]
    pts = np.zeros((N, M + 2, 3))
    dout = np.zeros((N, 3))
    opl_out = np.zeros(N)
    valid = np.ones(N, dtype=np.bool_)
    img = np.zeros((N, 3))
    sopl = np.zeros((N, M + 1))
    for i in numba.prange(N):
        px, py, pz = p0[i, 0], p0[i, 1], p0[i, 2]
        dx, dy, dz = d0[i, 0], d0[i, 1], d0[i, 2]
        nn = np.sqrt(dx * dx + dy * dy + dz * dz)
        dx /= nn
        dy /= nn
        dz /= nn
        pts[i, 0, 0] = px
        pts[i, 0, 1] = py
        pts[i, 0, 2] = pz
        opl = 0.0
        ncur = n_start
        ok_all = True
        for j in range(M):
            # to the surface's local frame
            vx, vy, vz = px - origin[j, 0], py - origin[j, 1], pz - origin[j, 2]
            if ident[j]:
                lx, ly, lz = vx, vy, vz
                ldx, ldy, ldz = dx, dy, dz
            else:
                R = rot[j]
                lx = vx * R[0, 0] + vy * R[1, 0] + vz * R[2, 0]
                ly = vx * R[0, 1] + vy * R[1, 1] + vz * R[2, 1]
                lz = vx * R[0, 2] + vy * R[1, 2] + vz * R[2, 2]
                ldx = dx * R[0, 0] + dy * R[1, 0] + dz * R[2, 0]
                ldy = dx * R[0, 1] + dy * R[1, 1] + dz * R[2, 1]
                ldz = dx * R[0, 2] + dy * R[1, 2] + dz * R[2, 2]
            # intersection
            t0 = -lz / ldz if ldz != 0.0 else np.inf
            ok = np.isfinite(t0)
            qx, qy, qz = lx + t0 * ldx, ly + t0 * ldy, lz + t0 * ldz
            cj, kj = c[j], k[j]
            if kind[j] == _PLANE or cj == 0.0:
                t = t0
                hx, hy, hz = qx, qy, qz
            else:
                A = cj * (ldx * ldx + ldy * ldy) + cj * (1.0 + kj) * ldz * ldz
                B = 2.0 * (cj * (qx * ldx + qy * ldy) - ldz)
                C = cj * (qx * qx + qy * qy)
                disc = B * B - 4.0 * A * C
                if not (disc >= 0.0):
                    ok = False
                sq = np.sqrt(disc) if disc >= 0.0 else 0.0
                denom = B + (sq if B >= 0.0 else -sq)
                dt = -2.0 * C / denom if abs(denom) > 0.0 else 0.0
                t = t0 + dt
                hx, hy, hz = qx + dt * ldx, qy + dt * ldy, qz + dt * ldz
                r2 = hx * hx + hy * hy
                if not (1.0 - (1.0 + kj) * cj * cj * r2 >= 0.0) or not np.isfinite(t):
                    ok = False
            if not (t > -1e-12):
                ok = False
            if not ok:
                ok_all = False
                hx, hy, hz = lx, ly, lz
                t = 0.0
            opl += ncur * t
            if clip and semi[j] >= 0.0:
                if np.sqrt(hx * hx + hy * hy) > semi[j] * (1 + 1e-9) + 1e-12:
                    ok_all = False
            # direction change
            if kind[j] != _PLANE:
                nx = -cj * hx
                ny = -cj * hy
                nz = 1.0 - cj * (1.0 + kj) * hz
                nl = np.sqrt(nx * nx + ny * ny + nz * nz)
                nx /= nl
                ny /= nl
                nz /= nl
                cos_i = ldx * nx + ldy * ny + ldz * nz
                if kind[j] == _REFLECT:
                    ldx -= 2.0 * cos_i * nx
                    ldy -= 2.0 * cos_i * ny
                    ldz -= 2.0 * cos_i * nz
                else:
                    if cos_i < 0.0:
                        nx, ny, nz = -nx, -ny, -nz
                        cos_i = -cos_i
                    mu = n1[j] / n2[j]
                    rad = 1.0 - mu * mu * (1.0 - cos_i * cos_i)
                    if not (rad >= 0.0):
                        ok_all = False
                    cos_t = np.sqrt(rad) if rad > 0.0 else 0.0
                    f = cos_t - mu * cos_i
                    ldx = mu * ldx + f * nx
                    ldy = mu * ldy + f * ny
                    ldz = mu * ldz + f * nz
                    ncur = n2[j]
            # back to the global frame
            if ident[j]:
                px, py, pz = hx + origin[j, 0], hy + origin[j, 1], hz + origin[j, 2]
                dx, dy, dz = ldx, ldy, ldz
            else:
                R = rot[j]
                px = hx * R[0, 0] + hy * R[0, 1] + hz * R[0, 2] + origin[j, 0]
                py = hx * R[1, 0] + hy * R[1, 1] + hz * R[1, 2] + origin[j, 1]
                pz = hx * R[2, 0] + hy * R[2, 1] + hz * R[2, 2] + origin[j, 2]
                dx = ldx * R[0, 0] + ldy * R[0, 1] + ldz * R[0, 2]
                dy = ldx * R[1, 0] + ldy * R[1, 1] + ldz * R[1, 2]
                dz = ldx * R[2, 0] + ldy * R[2, 1] + ldz * R[2, 2]
            nn = np.sqrt(dx * dx + dy * dy + dz * dz)
            dx /= nn
            dy /= nn
            dz /= nn
            pts[i, j + 1, 0] = px
            pts[i, j + 1, 1] = py
            pts[i, j + 1, 2] = pz
            sopl[i, j] = opl
            if kind[j] != _REFRACT:
                ncur = n2[j]
        # image plane
        vx, vy, vz = px - img_o[0], py - img_o[1], pz - img_o[2]
        lx = vx * img_R[0, 0] + vy * img_R[1, 0] + vz * img_R[2, 0]
        ly = vx * img_R[0, 1] + vy * img_R[1, 1] + vz * img_R[2, 1]
        lz = vx * img_R[0, 2] + vy * img_R[1, 2] + vz * img_R[2, 2]
        ldx = dx * img_R[0, 0] + dy * img_R[1, 0] + dz * img_R[2, 0]
        ldy = dx * img_R[0, 1] + dy * img_R[1, 1] + dz * img_R[2, 1]
        ldz = dx * img_R[0, 2] + dy * img_R[1, 2] + dz * img_R[2, 2]
        t = -lz / ldz if ldz != 0.0 else np.inf
        if not np.isfinite(t):
            ok_all = False
            t = 0.0
        ix, iy, iz = lx + t * ldx, ly + t * ldy, lz + t * ldz
        opl += ncur * t
        gx = ix * img_R[0, 0] + iy * img_R[0, 1] + iz * img_R[0, 2] + img_o[0]
        gy = ix * img_R[1, 0] + iy * img_R[1, 1] + iz * img_R[1, 2] + img_o[1]
        gz = ix * img_R[2, 0] + iy * img_R[2, 1] + iz * img_R[2, 2] + img_o[2]
        img[i, 0], img[i, 1], img[i, 2] = gx, gy, gz
        pts[i, M + 1, 0], pts[i, M + 1, 1], pts[i, M + 1, 2] = gx, gy, gz
        sopl[i, M] = opl
        opl_out[i] = opl
        dout[i, 0], dout[i, 1], dout[i, 2] = dx, dy, dz
        valid[i] = ok_all
    return pts, dout, opl_out, valid, img, sopl


if AVAILABLE:  # pragma: no branch
    # prange is an ordinary range in the serial compilation
    _kernel_serial = numba.njit(cache=True)(_kernel_impl)
    _kernel_parallel = numba.njit(parallel=True, cache=True)(_kernel_impl)


def trace(seq, p0, d0, clip: bool):
    """(points, directions, opl, valid, image, n_image, surface_opl)."""
    kind, c, k, origin, rot, ident, semi, n1, n2 = _pack(seq)
    p0 = np.ascontiguousarray(p0, dtype=float)
    d0 = np.ascontiguousarray(d0, dtype=float)
    kernel = _kernel_parallel if len(p0) >= PARALLEL_MIN_RAYS else _kernel_serial
    pts, d, opl, valid, img, sopl = kernel(
        p0,
        d0,
        kind,
        c,
        k,
        origin,
        rot,
        ident,
        semi,
        n1,
        n2,
        float(seq.surfaces[0].n_before),
        np.ascontiguousarray(seq.image_origin, dtype=float),
        np.ascontiguousarray(seq.image_rotation, dtype=float),
        bool(clip),
    )
    n_cur = seq.surfaces[0].n_before
    for s in seq.surfaces:
        n_cur = s.n_after
    return pts, d, opl, valid, img, n_cur, sopl
