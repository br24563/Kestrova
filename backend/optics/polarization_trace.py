"""
Polarization ray tracing through a sequential system (R. A. Chipman,
G. Young and W. S. T. Lam, *Polarized Light and Optical Systems*, 2018,
ch. 9-10; G. Yun, K. Crabtree and R. A. Chipman, Appl. Opt. 50, 2855
(2011)).

Each ray carries a 3x3 polarization ray-tracing matrix P. At every surface
it is multiplied by

    P_j = tau_s s s^T + tau_p p' p^T + k' k^T,

with k, k' the ray directions before and after, s = k x eta / |k x eta|
(eta the surface normal), p = k x s and p' = k' x s. For transmission,
tau_s and tau_p are amplitude coefficients normalised so |tau|^2 is the
power transmittance of the ray: Fresnel at a bare surface, the thin-film
characteristic matrix at a coated one; their phases come from the
amplitude coefficients. An ideal mirror reflects with tau_s = -1, tau_p = +1
(no loss, no retardance); ideal (paraxial) lenses, stops and dummy
surfaces are non-polarizing.

A second matrix Q is traced with every interface non-polarizing (the same
geometry, |tau| = 1, no phase), so M = P Q^T leaves out the geometric
rotation of the polarization frame. In the plane across the exit ray, M
gives the ray's Jones matrix in a basis carried through the system without
polarization change. From it come:
- the polarization-averaged power transmittance (sigma_1^2 + sigma_2^2) / 2;
- the diattenuation (sigma_1^2 - sigma_2^2) / (sigma_1^2 + sigma_2^2);
- the retardance, the phase difference of the eigenvalues of its unitary
  polar factor.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy.linalg import polar

from . import raytrace as rt
from .coating_spec import CoatingSpec
from .coatings.layer import Layer
from .coatings.transfer_matrix import reflection_transmission
from .fields import gaussian_pupil, resolve_fields, wavelength_weights
from .materials import refractive_index
from .models import OpticalSystem


def _unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _layers(spec: dict, wavelength: float) -> list:
    """Thin-film layers (nm, complex index) of a coating at a wavelength."""
    c = CoatingSpec.model_validate(spec)
    out = []
    for layer in c.layers:
        if layer.n is not None:
            n = layer.n
        else:
            assert layer.material is not None  # a layer has a material or an n
            n = refractive_index(layer.material, wavelength)
        out.append(
            Layer(
                material=layer.material or "",
                thickness=layer.thickness * 1e9,
                n=complex(n, -layer.k),
            )
        )
    return out


def transmission_coefficients(
    n1: float, n2: float, cos_i, wavelength: float, coating: Optional[dict] = None
):
    """(tau_s, tau_p) arrays: power-normalised amplitude transmission
    coefficients (|tau|^2 = power transmittance) at incidence cosines cos_i."""
    cos_i = np.clip(np.asarray(cos_i, dtype=float), 0.0, 1.0)
    if coating is None or not coating.get("layers"):
        sin2_t = (n1 / n2) ** 2 * (1.0 - cos_i**2)
        cos_t = np.sqrt(np.clip(1.0 - sin2_t, 0.0, None))
        ts = 2 * n1 * cos_i / (n1 * cos_i + n2 * cos_t)
        tp = 2 * n1 * cos_i / (n2 * cos_i + n1 * cos_t)
        with np.errstate(divide="ignore", invalid="ignore"):
            f = np.where(cos_i > 0, np.sqrt(n2 * cos_t / (n1 * cos_i)), 0.0)
        ok = sin2_t < 1.0
        return np.where(ok, ts * f, 0.0).astype(complex), np.where(
            ok, tp * f, 0.0
        ).astype(complex)
    layers = _layers(coating, wavelength)
    taus = []
    for pol in ("s", "p"):
        vals = []
        for c in cos_i.ravel():
            angle = math.acos(min(1.0, float(c)))
            _, T, _, t = reflection_transmission(
                layers, wavelength * 1e9, n1, n2, angle, pol
            )
            vals.append(math.sqrt(max(T, 0.0)) * np.exp(1j * np.angle(t)))
        taus.append(np.array(vals, dtype=complex).reshape(cos_i.shape))
    return taus[0], taus[1]


def _surface_normals(s, points):
    """Unit normals (global) of a sequence surface at global points."""
    pl = (points - s.origin) @ s.rotation  # to the local frame
    gx, gy = s.shape.grad(pl[:, 0], pl[:, 1])
    nl = np.stack([-gx, -gy, np.ones_like(gx)], axis=1)
    nl = _unit(nl)
    return nl @ s.rotation.T


def _perpendicular(k):
    """A unit vector across each direction (for normal incidence)."""
    a = np.where(
        np.abs(k[:, :1]) < 0.9, np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 1.0, 0.0]])
    )
    return _unit(np.cross(k, a))


def _interface(k_in, k_out, normal, ts, tp):
    """The polarization ray-tracing matrices of one interface (N, 3, 3)."""
    s = np.cross(k_in, normal)
    ns = np.linalg.norm(s, axis=1, keepdims=True)
    s = np.where(ns > 1e-12, s / np.where(ns > 1e-12, ns, 1.0), _perpendicular(k_in))
    p_in = np.cross(k_in, s)
    p_out = np.cross(k_out, s)
    outer = lambda a, b: a[:, :, None] * b[:, None, :]  # noqa: E731
    return (
        ts[:, None, None] * outer(s, s)
        + tp[:, None, None] * outer(p_out, p_in)
        + outer(k_out, k_in)
    )


def polarization_rays(
    system: OpticalSystem,
    hx: float,
    hy: float,
    px,
    py,
    wavelength: Optional[float] = None,
    seq=None,
    fo=None,
) -> dict:
    """
    Polarization ray trace of pupil points (px, py) at field (hx, hy).
    Returns per ray: the entrance and exit directions, P and Q (3x3), and
    whether it passed.
    """
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength
    seq = seq or rt.build_sequence(system, wavelength)
    fo = fo or rt.first_order(system, seq=seq)
    px = np.atleast_1d(np.asarray(px, dtype=float))
    py = np.atleast_1d(np.asarray(py, dtype=float))
    b, _, _ = rt.trace_field_rays(system, hx, hy, px, py, seq=seq, fo=fo)
    pts = b.points
    N, M = pts.shape[0], len(seq.surfaces)
    # direction of each segment (start -> surface 1 -> ... -> image); a
    # zero-length segment (coincident surfaces) keeps the previous direction
    dirs = np.zeros((N, M + 1, 3))
    prev = None
    for j in range(M + 1):
        seg = pts[:, j + 1] - pts[:, j]
        length = np.linalg.norm(seg, axis=1, keepdims=True)
        d = seg / np.where(length > 1e-15, length, 1.0)
        if prev is not None:
            d = np.where(length > 1e-15, d, prev)
        dirs[:, j] = d
        prev = d
    P = np.repeat(np.eye(3, dtype=complex)[None], N, axis=0)
    Q = np.repeat(np.eye(3)[None], N, axis=0)
    for i, s in enumerate(seq.surfaces):
        if s.kind in ("stop", "dummy"):
            continue
        k_in, k_out = dirs[:, i], dirs[:, i + 1]
        hit = pts[:, i + 1]
        normal = _surface_normals(s, hit)
        if s.kind == "ideal":
            # non-polarizing; s from the plane of the deviation
            n_eff = _unit(
                np.where(
                    np.linalg.norm(k_out - k_in, axis=1, keepdims=True) > 1e-15,
                    k_out - k_in,
                    normal,
                )
            )
            one = np.ones(N, dtype=complex)
            Pj = _interface(k_in, k_out, n_eff, one, one)
            P = Pj @ P
            Q = Pj.real @ Q
            continue
        if s.kind == "reflect":
            ts = -np.ones(N, dtype=complex)
            tp = np.ones(N, dtype=complex)
            Pj = _interface(k_in, k_out, normal, ts, tp)
            P = Pj @ P
            Q = Pj.real @ Q
            continue
        cos_i = np.abs(np.sum(k_in * normal, axis=1))
        ts, tp = transmission_coefficients(
            s.n_before, s.n_after, cos_i, wavelength, getattr(s, "coating", None)
        )
        P = _interface(k_in, k_out, normal, ts, tp) @ P
        one = np.ones(N, dtype=complex)
        Q = _interface(k_in, k_out, normal, one, one).real @ Q
    return {
        "k_in": dirs[:, 0],
        "k_out": dirs[:, M],
        "P": P,
        "Q": Q,
        "valid": b.valid,
    }


def jones_matrices(rays: dict) -> np.ndarray:
    """(N, 2, 2) Jones matrices in an entrance basis (x' across the ray, near
    global x) carried to the exit by Q."""
    k = rays["k_in"]
    ex = np.array([1.0, 0.0, 0.0])
    x_in = _unit(ex - np.sum(ex * k, axis=1, keepdims=True) * k)
    y_in = np.cross(k, x_in)
    Q = rays["Q"]
    x_out = np.einsum("nij,nj->ni", Q, x_in)
    y_out = np.einsum("nij,nj->ni", Q, y_in)
    P = rays["P"]
    Px = np.einsum("nij,nj->ni", P, x_in)
    Py = np.einsum("nij,nj->ni", P, y_in)
    J = np.empty((len(k), 2, 2), dtype=complex)
    J[:, 0, 0] = np.sum(x_out * Px, axis=1)
    J[:, 0, 1] = np.sum(x_out * Py, axis=1)
    J[:, 1, 0] = np.sum(y_out * Px, axis=1)
    J[:, 1, 1] = np.sum(y_out * Py, axis=1)
    return J


def jones_properties(J: np.ndarray) -> dict:
    """Polarization-averaged transmittance, diattenuation and retardance
    (rad) of each Jones matrix."""
    sv = np.linalg.svd(J, compute_uv=False)
    s1, s2 = sv[:, 0] ** 2, sv[:, 1] ** 2
    T = 0.5 * (s1 + s2)
    with np.errstate(invalid="ignore", divide="ignore"):
        D = np.where(s1 + s2 > 0, (s1 - s2) / (s1 + s2), 0.0)
    ret = np.zeros(len(J))
    for n, j in enumerate(J):
        if s1[n] <= 0:
            continue
        U, _ = polar(j)
        e = np.linalg.eigvals(U)
        ret[n] = abs(np.angle(e[0] / e[1]))
    return {"transmittance": T, "diattenuation": D, "retardance": ret}


def _field(system: OpticalSystem, index: Optional[int]):
    tracing, fields = resolve_fields(system)
    k = len(fields) - 1 if index is None else index
    if not 0 <= k < len(fields):
        raise ValueError(
            f"Field {k} does not exist (the field table has {len(fields)})"
        )
    return tracing, fields[k]


def pupil_map(
    system: OpticalSystem,
    field: Optional[int] = 0,
    wavelength: Optional[float] = None,
    grid: int = 21,
) -> dict:
    """Transmittance, diattenuation and retardance over a square grid of the
    pupil at one field and wavelength (NaN outside the pupil or for blocked
    rays)."""
    tracing, f = _field(system, field)
    wl = wavelength or system.analysis_settings.wavelength
    u = np.linspace(-1.0, 1.0, int(grid))
    X, Y = np.meshgrid(u, u)
    inside = X**2 + Y**2 <= 1.0 + 1e-12
    rays = polarization_rays(tracing, f.hx, f.hy, X[inside], Y[inside], wl)
    props = jones_properties(jones_matrices(rays))
    out = {}
    for key, v in props.items():
        m = np.full(X.shape, np.nan)
        vals = np.where(rays["valid"], v, np.nan)
        m[inside] = vals
        out[key] = m
    return {"pupil": u, "field": f.index, "wavelength": wl, **out}


def transmittance(
    system: OpticalSystem, field: Optional[int] = 0, rings: int = 6
) -> dict:
    """Polarization-averaged power transmittance at one field: averaged
    over the pupil (blocked rays count as 0) for each wavelength, and their
    weighted mean."""
    tracing, f = _field(system, field)
    px, py, w = gaussian_pupil(rings)
    per = []
    for wl in system.wavelengths:
        rays = polarization_rays(tracing, f.hx, f.hy, px, py, wl)
        T = jones_properties(jones_matrices(rays))["transmittance"]
        per.append(float(np.sum(w * np.where(rays["valid"], T, 0.0))))
    ww = wavelength_weights(system)
    return {
        "field": f.index,
        "wavelengths": list(system.wavelengths),
        "per_wavelength": per,
        "transmittance": float(np.dot(per, ww)),
    }
