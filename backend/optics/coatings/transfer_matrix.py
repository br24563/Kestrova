"""
Transfer (characteristic) matrix method for multilayer thin films
(H. A. Macleod, *Thin-Film Optical Filters*, ch. 2).

Indices are complex N = n - ik. For a layer of index N and physical
thickness d at angle theta inside it:

    delta = 2 pi N d cos(theta) / lambda
    eta_s = N cos(theta),   eta_p = N / cos(theta)
    M = [[cos delta, i sin(delta)/eta], [i eta sin(delta), cos delta]]

[B; C] = M_1 ... M_q [1; eta_substrate],  r = (eta_0 B - C)/(eta_0 B + C),
t = 2 eta_0 / (eta_0 B + C),  T = 4 eta_0 Re(eta_s) / |eta_0 B + C|^2.
Wavelengths and thicknesses are in nm; angles in radians in the incident
medium.
"""

from typing import Tuple

import numpy as np

from .layer import Layer


def _cos_in(n_incident, n_layer, angle):
    """cos(theta) inside a medium from Snell's invariant, on the branch with
    a decaying (not growing) field for the n - ik convention."""
    s = n_incident * np.sin(angle) / n_layer
    c = np.lib.scimath.sqrt(1 - s * s) if np.isrealobj(s) else np.sqrt(1 - s * s + 0j)
    c = complex(c)
    if c.imag > 0 or (c.imag == 0 and c.real < 0):
        c = -c
    return c


def _admittance(n, cos_t, polarization):
    if polarization == "s":
        return n * cos_t
    if polarization == "p":
        return n / cos_t
    raise ValueError("polarization must be 's' or 'p'")


def layer_matrix(layer: Layer, wavelength: float, angle: float = 0.0,
                 polarization: str = "s", n_incident: float = 1.0) -> np.ndarray:
    """Characteristic matrix of one layer."""
    n = layer.n
    cos_t = _cos_in(n_incident, n, angle)
    delta = 2 * np.pi * n * layer.thickness * cos_t / wavelength
    eta = _admittance(n, cos_t, polarization)
    return np.array([[np.cos(delta), 1j * np.sin(delta) / eta],
                     [1j * eta * np.sin(delta), np.cos(delta)]], dtype=complex)


def transfer_matrix(layers: list, wavelength: float, angle: float = 0.0,
                    polarization: str = "s", n_incident: float = 1.0) -> np.ndarray:
    """Product of the layer matrices, incident side first."""
    M = np.eye(2, dtype=complex)
    for layer in layers:
        M = M @ layer_matrix(layer, wavelength, angle, polarization, n_incident)
    return M


def _ends(n_incident, n_substrate, angle, polarization):
    eta0 = _admittance(n_incident, _cos_in(n_incident, n_incident, angle), polarization)
    etas = _admittance(n_substrate, _cos_in(n_incident, n_substrate, angle), polarization)
    return eta0, etas


def reflection_transmission(layers: list, wavelength: float, n_incident: float = 1.0,
                            n_substrate: float = 1.5, angle: float = 0.0,
                            polarization: str = "s") -> Tuple[float, float, complex, complex]:
    """(R, T, r, t) of a multilayer on a substrate."""
    M = transfer_matrix(layers, wavelength, angle, polarization, n_incident)
    eta0, etas = _ends(n_incident, n_substrate, angle, polarization)
    B, C = M @ np.array([1.0, etas])
    denom = eta0 * B + C
    r = (eta0 * B - C) / denom
    t = 2 * eta0 / denom
    R = float(abs(r) ** 2)
    T = float(4 * eta0.real * etas.real / abs(denom) ** 2)
    return R, T, r, t


def electric_field(layers: list, wavelength: float, n_incident: float = 1.0,
                   n_substrate: float = 1.5, angle: float = 0.0,
                   polarization: str = "s") -> np.ndarray:
    """
    |E| (tangential, relative to the incident wave) at each interface: the
    front surface, every internal interface, and the substrate.
    """
    eta0, etas = _ends(n_incident, n_substrate, angle, polarization)
    mats = [layer_matrix(l, wavelength, angle, polarization, n_incident) for l in layers]
    BC = [np.array([1.0, etas], dtype=complex)]
    for M in reversed(mats):
        BC.append(M @ BC[-1])
    BC = BC[::-1]                       # BC[0] = front surface, BC[-1] = substrate
    B0, C0 = BC[0]
    scale = 2 * eta0 / (eta0 * B0 + C0)
    return np.abs(np.array([scale * bc[0] for bc in BC]))
