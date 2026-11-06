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

    def pupil_values(px, py):
        """exp(i k W) at pupil points, 0 outside the pupil or for failed rays."""
        inside = _inside(px, py, vignetting)
        out = np.zeros(px.shape, dtype=complex)
        if inside.any():
            W, ok, _ = rt.opd(
                system,
                field_x,
                field_y,
                px[inside],
                py[inside],
                wavelength,
                seq=seq,
                fo=fo,
            )
            vals = np.where(ok, np.exp(2j * math.pi * np.nan_to_num(W) / wavelength), 0)
            out[inside] = vals
        return out

    def otf_along(angle: float) -> np.ndarray:
        e = np.array([math.sin(angle), math.cos(angle)])  # (x, y) of the shift
        ep = np.array([e[1], -e[0]])
        result = []
        area = None
        for delta in [0.0, *(2.0 * np.asarray(frequencies, dtype=float) / cutoff)]:
            if delta >= 2.0:
                result.append(0.0)
                continue
            half = 1.0 - delta / 2.0  # u range of the overlap of two unit disks
            u = half * x
            wu = half * w
            h = np.sqrt(np.clip(1.0 - (np.abs(u) + delta / 2.0) ** 2, 0.0, None))
            U = u[:, None] * np.ones_like(x)[None, :]
            V = h[:, None] * x[None, :]
            Wt = wu[:, None] * h[:, None] * w[None, :]
            px, py = U * e[0] + V * ep[0], U * e[1] + V * ep[1]
            a = pupil_values(
                (px + delta / 2 * e[0]).ravel(), (py + delta / 2 * e[1]).ravel()
            )
            b = pupil_values(
                (px - delta / 2 * e[0]).ravel(), (py - delta / 2 * e[1]).ravel()
            )
            value = np.sum(Wt.ravel() * a * np.conj(b))
            if area is None:
                area = value.real
                if area <= 0:
                    raise ValueError("No rays reach the image for this field")
                continue
            result.append(value / area)
        return np.asarray(result, dtype=complex)

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
