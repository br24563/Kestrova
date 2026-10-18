"""
Zernike polynomial calculations.

Three sets are provided:

- **Standard** (Noll 1976 ordering and normalisation): orthonormal over the
  unit disk, Z_j = sqrt(n+1) R_n^0 for m = 0 and sqrt(2(n+1)) R_n^|m| cos/sin
  (m theta) otherwise; even j carry cos, odd j carry sin. The RMS of a
  wavefront is then sqrt(sum c_j^2) over j >= 2.
- **Fringe** (University of Arizona ordering): un-normalised R_n^|m| times
  cos (m > 0) or sin (m < 0), ordered by (n + |m|)/2 then decreasing |m|.
- **Annular** (Mahajan 1981): orthonormal over the annulus eps <= rho <= 1,
  built here by Gram-Schmidt orthogonalisation of the radial powers.
"""

from functools import lru_cache
from math import factorial
from typing import Tuple

import numpy as np


def zernike_radial(n: int, m: int, rho: np.ndarray) -> np.ndarray:
    """Radial polynomial R_n^|m|(rho) (zero when n - |m| is odd)."""
    m = abs(m)
    rho = np.asarray(rho, dtype=float)
    if (n - m) % 2 != 0 or m > n:
        return np.zeros_like(rho)
    R = np.zeros_like(rho)
    for k in range((n - m) // 2 + 1):
        coeff = ((-1) ** k * factorial(n - k)) / (
            factorial(k) * factorial((n + m) // 2 - k) * factorial((n - m) // 2 - k)
        )
        R = R + coeff * rho ** (n - 2 * k)
    return R


def _noll_to_nm(j: int) -> Tuple[int, int]:
    """Noll index (1-based) to (n, m); m > 0 is the cosine term."""
    if j < 1:
        raise ValueError("Noll index starts at 1")
    n = 0
    j1 = j - 1
    while j1 > n:
        n += 1
        j1 -= n
    m = ((-1) ** j) * ((n % 2) + 2 * int((j1 + ((n + 1) % 2)) / 2))
    return n, m


def _fringe_to_nm(j: int) -> Tuple[int, int]:
    """Fringe index (1-based) to (n, m); m > 0 cosine, m < 0 sine."""
    if j < 1:
        raise ValueError("Fringe index starts at 1")
    k = int(np.floor(np.sqrt(j - 1)))
    pos = j - 1 - k * k  # position within group k (0 .. 2k)
    mag = k - pos // 2  # |m| decreases through the group
    n = 2 * k - mag
    if mag == 0:
        return n, 0
    return n, (mag if pos % 2 == 0 else -mag)  # cosine first, then sine


def zernike_standard(index: int, rho: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Noll-normalised Zernike polynomial Z_index(rho, theta)."""
    n, m = _noll_to_nm(index)
    rho = np.asarray(rho, dtype=float)
    theta = np.asarray(theta, dtype=float)
    R = zernike_radial(n, m, rho)
    if m == 0:
        return np.sqrt(n + 1.0) * R
    ang = np.cos(m * theta) if m > 0 else np.sin(-m * theta)
    return np.sqrt(2.0 * (n + 1.0)) * R * ang


def zernike_fringe(index: int, rho: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Fringe (un-normalised) Zernike polynomial."""
    n, m = _fringe_to_nm(index)
    R = zernike_radial(n, m, np.asarray(rho, dtype=float))
    if m == 0:
        return R
    theta = np.asarray(theta, dtype=float)
    return R * (np.cos(m * theta) if m > 0 else np.sin(-m * theta))


@lru_cache(maxsize=256)
def _annular_radial_coeffs(n: int, m: int, eps: float) -> tuple:
    """
    Power-series coefficients (in rho) of the annular radial polynomial
    R_n^m(rho; eps), orthogonal over [eps, 1] with weight rho and normalised
    so that int_eps^1 R^2 rho drho = (1 - eps^2) / (2 (n + 1)).
    """
    m = abs(m)
    x, w = np.polynomial.legendre.leggauss(200)
    r = eps + (1 - eps) * (x + 1) / 2
    w = w * (1 - eps) / 2 * r  # include the rho weight
    basis: list = []
    for nn in range(m, n + 1, 2):
        v = np.zeros(nn + 1)
        v[nn] = 1.0
        for b in basis:
            vb = np.polynomial.polynomial.polyval(r, v)
            bb = np.polynomial.polynomial.polyval(r, b)
            proj = np.sum(vb * bb * w) / np.sum(bb * bb * w)
            vv = np.zeros(max(len(v), len(b)))
            vv[: len(v)] += v
            vv[: len(b)] -= proj * np.asarray(b)
            v = vv
        val = np.polynomial.polynomial.polyval(r, v)
        target = (1 - eps**2) / (2 * (nn + 1))
        v = v * np.sqrt(target / np.sum(val * val * w))
        if np.polynomial.polynomial.polyval(1.0, v) < 0:
            v = -v
        basis.append(v)
    return tuple(basis[-1])


def zernike_annular(
    index: int, rho: np.ndarray, theta: np.ndarray, epsilon: float
) -> np.ndarray:
    """
    Annular Zernike polynomial (Noll ordering), orthonormal over the annulus
    epsilon <= rho <= 1. Reduces to :func:`zernike_standard` for epsilon = 0.
    """
    if not 0.0 <= epsilon < 1.0:
        raise ValueError("Obscuration ratio must satisfy 0 <= epsilon < 1")
    if epsilon < 1e-12:
        return zernike_standard(index, rho, theta)
    n, m = _noll_to_nm(index)
    rho = np.asarray(rho, dtype=float)
    theta = np.asarray(theta, dtype=float)
    R = np.polynomial.polynomial.polyval(
        rho, _annular_radial_coeffs(n, abs(m), float(epsilon))
    )
    # with R normalised as above, the mean square over the annulus is 1
    norm = np.sqrt(2.0 * (n + 1.0))
    if m == 0:
        return norm / np.sqrt(2.0) * R
    ang = np.cos(m * theta) if m > 0 else np.sin(-m * theta)
    return norm * R * ang


def _basis(kind: str):
    if kind == "fringe":
        return zernike_fringe
    if kind == "standard":
        return zernike_standard
    raise ValueError(f"Unknown Zernike type '{kind}' (use 'standard' or 'fringe')")


def zernike_fit(
    wavefront: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    num_terms: int = 37,
    zernike_type: str = "standard",
) -> np.ndarray:
    """
    Least-squares Zernike coefficients of wavefront samples at normalised
    pupil coordinates (x, y); samples outside the unit circle or NaN are
    ignored.
    """
    wavefront = np.asarray(wavefront, dtype=float)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    rho = np.hypot(x, y)
    theta = np.arctan2(y, x)
    mask = (rho <= 1.0 + 1e-12) & np.isfinite(wavefront)
    f = _basis(zernike_type)
    A = np.stack(
        [f(j, rho[mask], theta[mask]) for j in range(1, num_terms + 1)], axis=1
    )
    coeffs, *_ = np.linalg.lstsq(A, wavefront[mask], rcond=None)
    return coeffs


def zernike_evaluate(
    coefficients: np.ndarray,
    rho: np.ndarray,
    theta: np.ndarray,
    zernike_type: str = "standard",
) -> np.ndarray:
    """Sum of coefficient-weighted Zernike polynomials."""
    f = _basis(zernike_type)
    out = np.zeros(np.broadcast(np.asarray(rho), np.asarray(theta)).shape)
    for i, c in enumerate(coefficients):
        if c:
            out = out + c * f(i + 1, rho, theta)
    return out


def wavefront_to_zernike(
    wavefront: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    num_terms: int = 37,
) -> dict:
    """Standard Zernike fit with the RMS (excluding piston) and P-V."""
    coeffs = zernike_fit(wavefront, x, y, num_terms)
    w = np.asarray(wavefront, dtype=float)
    mask = (np.hypot(x, y) <= 1.0) & np.isfinite(w)
    return {
        "coefficients": coeffs.tolist(),
        "rms_wavefront": float(np.sqrt(np.sum(coeffs[1:] ** 2))),
        "pv_wavefront": float(np.ptp(w[mask])) if mask.any() else 0.0,
        "primary_aberrations": _identify_aberrations(coeffs),
    }


def zernike_to_wavefront(
    coefficients: np.ndarray,
    grid_size: int = 128,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate standard Zernike coefficients on a square grid (0 outside the pupil)."""
    g = np.linspace(-1, 1, grid_size)
    X, Y = np.meshgrid(g, g)
    rho = np.hypot(X, Y)
    theta = np.arctan2(Y, X)
    mask = rho <= 1.0
    wavefront = np.zeros((grid_size, grid_size))
    wavefront[mask] = zernike_evaluate(coefficients, rho[mask], theta[mask])
    return wavefront, X, Y


def _identify_aberrations(coeffs: np.ndarray) -> dict:
    """Named primary terms of a Noll-ordered coefficient vector."""
    names = {
        2: "tilt_x",
        3: "tilt_y",
        4: "defocus",
        5: "astigmatism_45",
        6: "astigmatism_0",
        7: "coma_y",
        8: "coma_x",
        9: "trefoil_y",
        10: "trefoil_x",
        11: "spherical_primary",
    }
    return {name: float(coeffs[j - 1]) for j, name in names.items() if j <= len(coeffs)}


def _zernike_name(n: int, m: int) -> str:
    """Conventional name of the (n, m) term (m > 0 cosine, m < 0 sine)."""
    if n == 0:
        return "Piston"
    table = {
        (1, 1): "X Tilt",
        (1, -1): "Y Tilt",
        (2, 0): "Defocus",
        (2, -2): "Astigmatism 45",
        (2, 2): "Astigmatism 0",
        (3, -1): "Coma Y",
        (3, 1): "Coma X",
        (3, -3): "Trefoil Y",
        (3, 3): "Trefoil X",
        (4, 0): "Spherical Primary",
        (4, 2): "Secondary Astigmatism 0",
        (4, -2): "Secondary Astigmatism 45",
        (4, 4): "Tetrafoil 0",
        (4, -4): "Tetrafoil 45",
        (5, 1): "Secondary Coma X",
        (5, -1): "Secondary Coma Y",
        (6, 0): "Secondary Spherical",
    }
    return table.get((n, m), f"Z(n={n}, m={m})")


def zernike_names(num_terms: int, zernike_type: str = "standard") -> list:
    conv = _noll_to_nm if zernike_type == "standard" else _fringe_to_nm
    return [_zernike_name(*conv(j)) for j in range(1, num_terms + 1)]


def zernike_coeffs(num_terms: int = 37, zernike_type: str = "standard") -> list[dict]:
    """Index, (n, m) and name of each term."""
    conv = _noll_to_nm if zernike_type == "standard" else _fringe_to_nm
    out = []
    for i in range(1, num_terms + 1):
        n, m = conv(i)
        out.append({"index": i, "n": n, "m": m, "name": _zernike_name(n, m)})
    return out
