"""
Diffraction MTF by two independent methods, through focus and across field.

- **FFT** (:func:`optics.pupil.mtf`): the autocorrelation of the pupil
  function sampled on a square grid, by FFT.
- **Hopkins direct integration** (:func:`hopkins_otf`): for each frequency,
  the overlap integral of the pupil function with its shifted copy,
  OTF(s) = (1/A) integral P(p + s/2) P*(p - s/2) dp, evaluated by
  Gauss-Legendre quadrature over the exact overlap region, with the real
  wavefront traced at the quadrature points themselves (no grid, no
  interpolation, no aliasing). H. H. Hopkins, Proc. Phys. Soc. B 70, 449
  (1957).

Pupil coordinates are the normalised stop coordinates of
:func:`optics.pupil.wavefront_grid`; a shift of 2 (the pupil diameter)
corresponds to the cutoff frequency 2 NA' / lambda. Polychromatic OTFs are
the weighted sums of the complex OTFs of each wavelength, each normalised
to 1 at zero frequency. Frequencies are in cycles/mm at the interface.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional, Sequence, Union

import numpy as np

from . import pupil as pp
from . import raytrace as rt
from .fields import resolve_fields, wavelength_weights
from .models import ImagePlane, OpticalSystem

#: Frequencies or other values: a list or a NumPy array.
Values = Union[Sequence[float], np.ndarray]


def diffraction_limited_mtf(normalized_frequency) -> np.ndarray:
    """MTF of an aberration-free circular pupil at nu / nu_cutoff:
    (2/pi) (acos x - x sqrt(1 - x^2)), zero beyond the cutoff."""
    x = np.clip(np.asarray(normalized_frequency, dtype=float), 0.0, 1.0)
    return (2.0 / math.pi) * (np.arccos(x) - x * np.sqrt(1.0 - x * x))


def _defocused(system: OpticalSystem, defocus: float, wavelength=None):
    """The system with its image plane moved by ``defocus`` (m, along the
    direction of travel), as :func:`optics.pupil.wavefront_grid` does."""
    if not defocus:
        return system
    seq = rt.build_sequence(system, wavelength)
    return system.model_copy(
        update={
            "image_plane": ImagePlane(
                position=system.image_plane.position + defocus * seq.image_direction
            )
        }
    )


def _inside(px, py, vignetting) -> np.ndarray:
    cx, cy, ax, ay = pp.vignetted_pupil(vignetting)
    return ((px - cx) / ax) ** 2 + ((py - cy) / ay) ** 2 <= 1.0 + 1e-12


#: Pupil points traced per call (bounds the memory of a large batch).
_CHUNK = 100_000


@lru_cache(maxsize=64)
def _gauss_nodes(n: int) -> tuple:
    x, w = np.polynomial.legendre.leggauss(n)
    return tuple(x), tuple(w)


def _gauss_rule(n: int):
    """Gauss-Legendre nodes and weights on [-1, 1]."""
    x, w = _gauss_nodes(n)
    return np.array(x), np.array(w)


def _runs(ok_row) -> list:
    """(first, last) index of each run of True in a boolean row."""
    runs = []
    j, n = 0, len(ok_row)
    while j < n:
        if not ok_row[j]:
            j += 1
            continue
        k = j
        while k + 1 < n and ok_row[k + 1]:
            k += 1
        runs.append((j, k))
        j = k + 1
    return runs


def _overlap_integrals(pair, shifts, x, w, bisections: int = 16) -> np.ndarray:
    """
    Integrals of a conj(b) over the overlaps of two unit pupils sheared by
    +-shifts[k] along u (|u| <= 1 - shifts[k]), for every k at once, by
    Gauss quadrature across (v) Gauss lines in u. ``pair(u, v, k)`` gives
    the pupil values a and b at the sheared points (0 where a ray is blocked
    or misses).

    When every quadrature point of an overlap passes, its integral is the
    plain product rule. When some are blocked (an obscuration, a shaped
    aperture, vignetting by any surface) the integrand has edges inside the
    domain, which Gauss quadrature integrates poorly. Each line is then
    split at its edges (found by probing and bisection) so every unblocked
    piece gets its own Gauss interval, and the u range is split into panels
    where the number of pieces changes (a line grazing an edge), so each
    panel's line integrals vary smoothly. Every stage traces all overlaps
    together.
    """
    shifts = np.asarray(shifts, dtype=float)
    K, nq = len(shifts), len(x)
    halves = 1.0 - shifts
    out = np.zeros(K, dtype=complex)
    if K == 0:
        return out

    def h_of(u, k):
        return np.sqrt(np.clip(1.0 - (np.abs(u) + shifts[k]) ** 2, 0.0, None))

    def passes(a, b):
        return (np.abs(a) > 0) & (np.abs(b) > 0)

    # plain Gauss rule for every overlap
    u = halves[:, None] * x[None, :]
    wu = halves[:, None] * w[None, :]
    ks = np.repeat(np.arange(K), nq * nq)
    H = h_of(u, np.arange(K)[:, None])
    U = np.repeat(u[:, :, None], nq, axis=2)
    V = H[:, :, None] * x[None, None, :]
    a, b = pair(U.ravel(), V.ravel(), ks)
    weight = (wu[:, :, None] * H[:, :, None] * w[None, None, :]).reshape(K, -1)
    prod = (a * np.conj(b)).reshape(K, -1)
    clean = passes(a, b).reshape(K, -1).all(axis=1)
    out[clean] = np.sum(weight * prod, axis=1)[clean]
    blocked = np.flatnonzero(~clean)
    if blocked.size == 0:
        return out

    # coarse probes: bisection then locates each edge to ~1e-5 of the pupil
    t = np.linspace(-1.0, 1.0, 2 * max(8, nq // 6) + 1)
    M = len(t)

    def probe(us, kk):
        """Pass/block of the probe points of each line (u, overlap)."""
        Vp = h_of(us, kk)[:, None] * t[None, :]
        a, b = pair(np.repeat(us, M), Vp.ravel(), np.repeat(kk, M))
        return passes(a, b).reshape(len(us), M)

    # panels in u: split where the number of unblocked pieces changes
    ub = u[blocked]
    kb = np.repeat(blocked, nq)
    counts = np.array([len(_runs(r)) for r in probe(ub.ravel(), kb)]).reshape(
        len(blocked), nq
    )
    brk_k, brk_lo, brk_hi, brk_c = [], [], [], []
    for row, k in enumerate(blocked):
        for i in range(nq - 1):
            if counts[row, i] != counts[row, i + 1]:
                brk_k.append(k)
                brk_lo.append(ub[row, i])
                brk_hi.append(ub[row, i + 1])
                brk_c.append(counts[row, i])
    panel_edges = {int(k): [-halves[k], halves[k]] for k in blocked}
    if brk_k:
        bk = np.array(brk_k)
        lo, hi, c0 = np.array(brk_lo), np.array(brk_hi), np.array(brk_c)
        for _ in range(bisections):
            mid = 0.5 * (lo + hi)
            same = np.array([len(_runs(r)) for r in probe(mid, bk)]) == c0
            lo = np.where(same, mid, lo)
            hi = np.where(same, hi, mid)
        for k, edge in zip(bk, 0.5 * (lo + hi)):
            panel_edges[int(k)].append(float(edge))
    # Gauss lines in each panel, in proportion to its width
    line_u, line_w, line_k = [], [], []
    for kp, edges in panel_edges.items():
        e_ = sorted(edges)
        total = e_[-1] - e_[0]
        for lo_, hi_ in zip(e_[:-1], e_[1:]):
            xp, wp = _gauss_rule(max(8, math.ceil(nq * (hi_ - lo_) / total)))
            line_u.append(0.5 * (lo_ + hi_) + 0.5 * (hi_ - lo_) * xp)
            line_w.append(0.5 * (hi_ - lo_) * wp)
            line_k.append(np.full(len(xp), kp))
    LU = np.concatenate(line_u)
    LW = np.concatenate(line_w)
    LK = np.concatenate(line_k)
    LH = h_of(LU, LK)

    # pieces of each line, their edges found by bisection
    seg_line: list[int] = []
    v_lo: list[float] = []
    v_hi: list[float] = []
    todo: list[tuple] = []
    for i, row in enumerate(probe(LU, LK)):
        for j, k_ in _runs(row):
            s_ = len(seg_line)
            seg_line.append(i)
            v_lo.append(LH[i] * t[j])
            v_hi.append(LH[i] * t[k_])
            if j > 0:
                todo.append((s_, 0, LH[i] * t[j], LH[i] * t[j - 1]))
            if k_ < M - 1:
                todo.append((s_, 1, LH[i] * t[k_], LH[i] * t[k_ + 1]))
    if not seg_line:
        return out
    seg_line_a = np.array(seg_line)
    v_lo_a, v_hi_a = np.array(v_lo), np.array(v_hi)
    if todo:
        seg = np.array([e_[0] for e_ in todo])
        side = np.array([e_[1] for e_ in todo])
        good = np.array([e_[2] for e_ in todo], dtype=float)
        bad = np.array([e_[3] for e_ in todo], dtype=float)
        ue, ke = LU[seg_line_a[seg]], LK[seg_line_a[seg]]
        for _ in range(bisections):
            mid = 0.5 * (good + bad)
            ok = passes(*pair(ue, mid, ke))
            good = np.where(ok, mid, good)
            bad = np.where(ok, bad, mid)
        edge = 0.5 * (good + bad)
        v_lo_a[seg[side == 0]] = edge[side == 0]
        v_hi_a[seg[side == 1]] = edge[side == 1]
    # Gauss points along each piece, in proportion to its share of the line
    mid, rad = 0.5 * (v_lo_a + v_hi_a), 0.5 * (v_hi_a - v_lo_a)
    share = rad / np.maximum(LH[seg_line_a], 1e-300)
    n_pts = np.maximum(8, np.ceil(nq * share)).astype(int)
    Ug, Vg, Wt, Kg = [], [], [], []
    for n in np.unique(n_pts):
        sel = n_pts == n
        xp, wp = _gauss_rule(int(n))
        Vg.append((mid[sel, None] + rad[sel, None] * xp[None, :]).ravel())
        Wt.append((LW[seg_line_a[sel]][:, None] * rad[sel, None] * wp[None, :]).ravel())
        Ug.append(np.repeat(LU[seg_line_a[sel]], n))
        Kg.append(np.repeat(LK[seg_line_a[sel]], n))
    Ug_a, Vg_a, Wt_a, Kg_a = (np.concatenate(z) for z in (Ug, Vg, Wt, Kg))
    a, b = pair(Ug_a, Vg_a, Kg_a)
    sums = np.zeros(K, dtype=complex)
    np.add.at(sums, Kg_a, Wt_a * a * np.conj(b))
    out[blocked] = sums[blocked]
    return out


def hopkins_otf(
    system: OpticalSystem,
    frequencies: Values,
    wavelength: Optional[float] = None,
    field_x: float = 0.0,
    field_y: float = 0.0,
    azimuth: float = 0.0,
    vignetting: Optional[tuple] = None,
    quadrature: int = 48,
) -> dict:
    """
    Monochromatic OTF by direct integration, tangential (along +y rotated
    by ``azimuth`` toward +x) and sagittal (across it), at ``frequencies``
    (cycles/m). Returns the complex OTFs and the cutoff (cycles/m).
    """
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength
    seq = rt.build_sequence(system, wavelength)
    fo = rt.first_order(system, seq=seq)
    na = pp.image_space_na(system, wavelength, seq=seq, fo=fo)
    if not na > 0:
        raise ValueError("Image space is afocal: the MTF in cycles/mm is undefined")
    cutoff = 2.0 * na / wavelength
    x, w = np.polynomial.legendre.leggauss(int(quadrature))

    chief = rt.chief_reference(system, field_x, field_y, seq, fo)

    def pupil_values(px, py):
        """exp(i k W) at pupil points, 0 outside the pupil or for failed rays."""
        inside = np.flatnonzero(_inside(px, py, vignetting))
        out = np.zeros(px.shape, dtype=complex)
        for start in range(0, inside.size, _CHUNK):
            idx = inside[start : start + _CHUNK]
            W, ok, _ = rt.opd(
                system,
                field_x,
                field_y,
                px[idx],
                py[idx],
                wavelength,
                seq=seq,
                fo=fo,
                chief=chief,
            )
            out[idx] = np.where(
                ok, np.exp(2j * math.pi * np.nan_to_num(W) / wavelength), 0
            )
        return out

    def otf_along(angle: float) -> np.ndarray:
        e = np.array([math.sin(angle), math.cos(angle)])  # (x, y) of the shift
        ep = np.array([e[1], -e[0]])
        deltas = 2.0 * np.asarray(frequencies, dtype=float) / cutoff
        shifts = np.concatenate([[0.0], np.where(deltas < 2.0, deltas, 0.0) / 2.0])

        def pair(uu, vv, kk):
            """Pupil values at the two points sheared by +-shifts[kk]."""
            px, py = uu * e[0] + vv * ep[0], uu * e[1] + vv * ep[1]
            sx, sy = shifts[kk] * e[0], shifts[kk] * e[1]
            both = pupil_values(
                np.concatenate([px + sx, px - sx]), np.concatenate([py + sy, py - sy])
            )
            return both[: len(px)], both[len(px) :]

        values = _overlap_integrals(pair, shifts, x, w)
        area = values[0].real
        if area <= 0:
            raise ValueError("No rays reach the image for this field")
        otf = values[1:] / area
        return np.where(deltas < 2.0, otf, 0.0)

    return {
        "frequency": np.asarray(frequencies, dtype=float),
        "tangential": otf_along(azimuth),
        "sagittal": otf_along(azimuth + math.pi / 2),
        "cutoff": cutoff,
    }


def _fft_otf(
    system, frequencies, wavelength, field_x, field_y, azimuth, vignetting, grid
) -> dict:
    g = pp.wavefront_grid(
        system, field_y, grid, wavelength, field_x=field_x, vignetting=vignetting
    )
    r = pp.mtf(g, azimuth=azimuth)
    f = np.asarray(frequencies, dtype=float)

    def interp(otf):
        re = np.interp(f, r.frequency, otf.real, right=0.0)
        im = np.interp(f, r.frequency, otf.imag, right=0.0)
        return re + 1j * im

    return {
        "frequency": f,
        "tangential": interp(r.otf_tangential),
        "sagittal": interp(r.otf_sagittal),
        "cutoff": r.cutoff,
    }


def polychromatic_otf(
    system: OpticalSystem,
    frequencies: Values,
    field_x: float = 0.0,
    field_y: float = 0.0,
    azimuth: float = 0.0,
    vignetting: Optional[tuple] = None,
    method: str = "fft",
    grid: int = 64,
    quadrature: int = 48,
) -> dict:
    """Weighted polychromatic OTF (frequencies in cycles/m) by either method,
    plus the polychromatic diffraction limit of the unvignetted pupil."""
    if method not in ("fft", "hopkins"):
        raise ValueError("method must be 'fft' or 'hopkins'")
    weights = wavelength_weights(system)
    f = np.asarray(frequencies, dtype=float)
    tan = np.zeros(f.size, dtype=complex)
    sag = np.zeros(f.size, dtype=complex)
    limit = np.zeros(f.size)
    cutoff = 0.0
    for wl, wt in zip(system.wavelengths, weights):
        if method == "hopkins":
            r = hopkins_otf(
                system, f, wl, field_x, field_y, azimuth, vignetting, quadrature
            )
        else:
            r = _fft_otf(system, f, wl, field_x, field_y, azimuth, vignetting, grid)
        tan += wt * r["tangential"]
        sag += wt * r["sagittal"]
        limit += wt * diffraction_limited_mtf(f / r["cutoff"])
        cutoff = max(cutoff, r["cutoff"])
    return {
        "frequency": f,
        "tangential": tan,
        "sagittal": sag,
        "diffraction_limit": limit,
        "cutoff": cutoff,
    }


def _field(system: OpticalSystem, index: int):
    tracing, fields = resolve_fields(system)
    if not 0 <= index < len(fields):
        raise ValueError(f"Field {index} does not exist ({len(fields)} fields)")
    return tracing, fields[index]


def mtf_curves(
    system: OpticalSystem,
    index: int = 0,
    frequencies_mm: Optional[Values] = None,
    method: str = "fft",
    grid: int = 64,
    quadrature: int = 48,
) -> dict:
    """Polychromatic MTF of one field-table entry (cycles/mm)."""
    tracing, f = _field(system, index)
    if frequencies_mm is None:
        cut = (
            max(2.0 * pp.image_space_na(tracing, wl) / wl for wl in system.wavelengths)
            / 1e3
        )
        frequencies_mm = np.linspace(0.0, cut, 41)
    fm = np.asarray(frequencies_mm, dtype=float)
    r = polychromatic_otf(
        tracing, fm * 1e3, f.hx, f.hy, f.azimuth, f.vignetting, method, grid, quadrature
    )
    return {
        "field": index,
        "method": method,
        "frequency_cyc_per_mm": fm.tolist(),
        "tangential": np.abs(r["tangential"]).tolist(),
        "sagittal": np.abs(r["sagittal"]).tolist(),
        "diffraction_limit": r["diffraction_limit"].tolist(),
        "cutoff_cyc_per_mm": r["cutoff"] / 1e3,
    }


def best_focus_shift(
    system: OpticalSystem,
    field_x: float = 0.0,
    field_y: float = 0.0,
    vignetting: Optional[tuple] = None,
    grid: int = 32,
    step: float = 1e-6,
) -> float:
    """
    Image-plane shift (m) minimising the RMS wavefront error at the
    analysis wavelength (piston removed): W(z) is linear in z to first order,
    so z* = -<W0 - mean, G> / <G, G> with G = dW/dz by a central difference.
    """
    lam = system.analysis_settings.wavelength

    def wave(dz):
        g = pp.wavefront_grid(
            _defocused(system, dz),
            field_y,
            grid,
            lam,
            field_x=field_x,
            vignetting=vignetting,
        )
        return g.W, g.mask

    W0, m0 = wave(0.0)
    Wp, mp = wave(step)
    Wm, mm = wave(-step)
    m = m0 & mp & mm
    if not m.any():
        raise ValueError("No rays reach the image for this field")
    w0 = W0[m] - W0[m].mean()
    G = (Wp[m] - Wm[m]) / (2 * step)
    G = G - G.mean()
    gg = float(G @ G)
    return -float(w0 @ G) / gg if gg > 0 else 0.0


def through_focus_mtf(
    system: OpticalSystem,
    frequency_mm: float,
    index: int = 0,
    defocus_range: Optional[tuple] = None,
    points: int = 21,
    method: str = "fft",
    grid: int = 48,
    quadrature: int = 32,
) -> dict:
    """
    Polychromatic MTF at one frequency against image-plane position, for one
    field-table entry.

    Default range: the best focus at a given frequency lies between the
    image plane (paraxial focus) and beyond the minimum-RMS-wavefront focus
    z* (:func:`best_focus_shift`); for an uncorrected lens these are far
    apart and the MTF may have several local peaks. So a coarse scan covers
    [min(0, z*), max(0, z*)] widened by max(s, |z*| / 4), s = 4 lambda N'^2
    (twice the diffraction depth of focus), and the returned scan spans +-s
    about the highest coarse point. For a corrected lens (z* ~ 0) that is
    just +-s about the image plane.

    Returns the best-focus positions (tangential, sagittal, and of their
    mean), the range over which the mean stays above half its peak, and
    whether the peak lies at an end of the scan (then it may lie beyond).
    """
    tracing, f = _field(system, index)
    if defocus_range is None:
        lam = system.analysis_settings.wavelength
        n_w = 1.0 / (2.0 * pp.image_space_na(tracing, lam))
        span = 4.0 * lam * n_w * n_w
        z_rms = best_focus_shift(tracing, f.hx, f.hy, f.vignetting)
        pad = max(span, abs(z_rms) / 4.0)
        lo, hi = min(0.0, z_rms) - pad, max(0.0, z_rms) + pad
        if hi - lo > 4.0 * span:
            coarse = np.linspace(lo, hi, 31)
            vals = []
            for d in coarse:
                r = polychromatic_otf(
                    _defocused(tracing, float(d)),
                    [frequency_mm * 1e3],
                    f.hx,
                    f.hy,
                    f.azimuth,
                    f.vignetting,
                    method,
                    grid,
                    quadrature,
                )
                vals.append(abs(r["tangential"][0]) + abs(r["sagittal"][0]))
            centre = float(coarse[int(np.argmax(vals))])
            span = max(span, 2.0 * (coarse[1] - coarse[0]))
        else:
            centre = 0.0
        defocus_range = (centre - span, centre + span)
        auto = True
    else:
        auto = False

    def scan(rng):
        zz = np.linspace(rng[0], rng[1], int(points))
        tt, ss = [], []
        for d in zz:
            r = polychromatic_otf(
                _defocused(tracing, float(d)),
                [frequency_mm * 1e3],
                f.hx,
                f.hy,
                f.azimuth,
                f.vignetting,
                method,
                grid,
                quadrature,
            )
            tt.append(float(abs(r["tangential"][0])))
            ss.append(float(abs(r["sagittal"][0])))
        return zz, np.array(tt), np.array(ss)

    z, tan_a, sag_a = scan(defocus_range)
    # an automatic range follows the peak if it lands on an edge
    for _ in range(3 if auto else 0):
        k = int(np.argmax(tan_a + sag_a))
        if k not in (0, len(z) - 1):
            break
        half = (z[-1] - z[0]) / 2
        shift = half if k == len(z) - 1 else -half
        z, tan_a, sag_a = scan((z[0] + shift, z[-1] + shift))
    tan, sag = tan_a.tolist(), sag_a.tolist()
    mean = 0.5 * (tan_a + sag_a)
    above = z[mean >= 0.5 * mean.max()]
    return {
        "field": index,
        "method": method,
        "frequency_cyc_per_mm": frequency_mm,
        "defocus_mm": (z * 1e3).tolist(),
        "tangential": tan,
        "sagittal": sag,
        "best_focus_mm": {
            "tangential": float(z[np.argmax(tan_a)] * 1e3),
            "sagittal": float(z[np.argmax(sag_a)] * 1e3),
            "mean": float(z[np.argmax(mean)] * 1e3),
        },
        "half_peak_range_mm": (
            float((above.max() - above.min()) * 1e3) if above.size >= 2 else 0.0
        ),
        "peak_at_scan_edge": bool(int(np.argmax(mean)) in (0, len(z) - 1)),
    }


def _interpolated_vignetting(fields, fraction: float) -> tuple:
    """Vignetting factors at a fraction of the largest field, linear in the
    radial field between the table entries (none without factors)."""
    rows = sorted((math.hypot(f.hx, f.hy), f.vignetting) for f in fields)
    radii = np.array([r for r, _ in rows])
    vig = np.array([v for _, v in rows], dtype=float)
    if len(rows) == 1:
        return tuple(vig[0])
    return tuple(float(np.interp(fraction, radii, vig[:, k])) for k in range(4))


def mtf_vs_field(
    system: OpticalSystem,
    frequencies_mm: Sequence[float] = (10.0, 30.0, 50.0),
    points: int = 11,
    method: str = "fft",
    grid: int = 48,
    quadrature: int = 32,
) -> dict:
    """
    Polychromatic tangential and sagittal MTF at each frequency from the
    axis to the largest field, along the direction of the largest field-table
    entry, with vignetting interpolated from the table.
    """
    tracing, fields = resolve_fields(system)
    far = max(fields, key=lambda f: math.hypot(f.hx, f.hy))
    r_far = math.hypot(far.hx, far.hy)
    dir_x, dir_y = (far.hx / r_far, far.hy / r_far) if r_far > 0 else (0.0, 1.0)
    azimuth = math.atan2(dir_x, dir_y) if r_far > 0 else 0.0
    fracs = np.linspace(0.0, 1.0, int(points)) * (r_far if r_far > 0 else 1.0)
    fm = np.asarray(frequencies_mm, dtype=float)
    tan = np.zeros((fracs.size, fm.size))
    sag = np.zeros((fracs.size, fm.size))
    for i, h in enumerate(fracs):
        r = polychromatic_otf(
            tracing,
            fm * 1e3,
            h * dir_x,
            h * dir_y,
            azimuth,
            _interpolated_vignetting(fields, float(h)),
            method,
            grid,
            quadrature,
        )
        tan[i] = np.abs(r["tangential"])
        sag[i] = np.abs(r["sagittal"])
    return {
        "method": method,
        "field_fraction": (fracs / (r_far if r_far > 0 else 1.0)).tolist(),
        "frequencies_cyc_per_mm": fm.tolist(),
        "tangential": tan.T.tolist(),  # one row per frequency
        "sagittal": sag.T.tolist(),
    }
