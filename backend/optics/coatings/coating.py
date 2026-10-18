"""
Coating design and analysis.

Provides pre-defined coating designs and analysis tools.
"""

from typing import Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
from .layer import Layer
from .transfer_matrix import reflection_transmission, electric_field


@dataclass
class Coating:
    """Multilayer thin film coating."""
    name: str = "Coating"
    layers: list[Layer] = field(default_factory=list)
    n_incident: float = 1.0  # Incident medium (air)
    n_substrate: float = 1.5  # Substrate
    
    def add_layer(self, material: str, thickness: float, n=None):
        """Add a layer (thickness in nm; index from the database unless given)."""
        self.layers.append(Layer(material=material, thickness=thickness, n=n))
    
    def reflectance(self, wavelength: float, angle: float = 0.0, polarization: str = 's') -> float:
        """Calculate reflectance at given wavelength."""
        R, _, _, _ = reflection_transmission(
            self.layers, wavelength, self.n_incident, self.n_substrate, angle, polarization
        )
        return R
    
    def transmittance(self, wavelength: float, angle: float = 0.0, polarization: str = 's') -> float:
        """Calculate transmittance at given wavelength."""
        _, T, _, _ = reflection_transmission(
            self.layers, wavelength, self.n_incident, self.n_substrate, angle, polarization
        )
        return T
    
    def absorption(self, wavelength: float, angle: float = 0.0, polarization: str = 's') -> float:
        """Calculate absorption."""
        R = self.reflectance(wavelength, angle, polarization)
        T = self.transmittance(wavelength, angle, polarization)
        return 1 - R - T
    
    def phase_shift(self, wavelength: float, angle: float = 0.0, polarization: str = 's') -> float:
        """Calculate phase shift on reflection."""
        _, _, r, _ = reflection_transmission(
            self.layers, wavelength, self.n_incident, self.n_substrate, angle, polarization
        )
        return np.angle(r)
    
    def field_distribution(self, wavelength: float, angle: float = 0.0, polarization: str = 's') -> np.ndarray:
        """Calculate electric field distribution."""
        return electric_field(
            self.layers, wavelength, self.n_incident, self.n_substrate, angle, polarization
        )
    
    def spectrum(self, wavelengths: np.ndarray, angle: float = 0.0, polarization: str = 's') -> dict:
        """Calculate spectral response."""
        wavelengths = np.asarray(wavelengths, dtype=float)
        R = np.zeros_like(wavelengths)
        T = np.zeros_like(wavelengths)
        
        for i, wl in enumerate(wavelengths):
            R[i] = self.reflectance(wl, angle, polarization)
            T[i] = self.transmittance(wl, angle, polarization)
        
        return {
            'wavelengths': wavelengths,
            'reflectance': R,
            'transmittance': T,
            'absorption': 1 - R - T
        }


def _index(material: str, wavelength: float) -> float:
    n = Layer(material, 1.0, design_wavelength=wavelength).n
    assert n is not None
    return n.real


def _qw(material: str, wavelength: float, factor: float = 1.0) -> Layer:
    """Layer of ``factor`` quarter waves at ``wavelength`` (nm)."""
    n = _index(material, wavelength)
    return Layer(material, factor * wavelength / (4.0 * n), design_wavelength=wavelength)


def design_ar_coating(wavelength: float = 550.0, n_substrate: float = 1.5,
                      material: str = "MgF2") -> Coating:
    """
    Single quarter-wave anti-reflection layer (MgF2 by default) at the
    design wavelength; residual R = ((ns - n^2)/(ns + n^2))^2 at normal
    incidence from air.
    """
    coating = Coating(name="AR_Coating", n_substrate=n_substrate)
    coating.layers.append(_qw(material, wavelength))
    return coating


def design_hr_coating(wavelength: float = 550.0, n_substrate: float = 1.5,
                      num_pairs: int = 10, high_index: str = "TiO2",
                      low_index: str = "SiO2") -> Coating:
    """Quarter-wave high reflector (HL)^p H at the design wavelength."""
    coating = Coating(name="HR_Mirror", n_substrate=n_substrate)
    for _ in range(num_pairs):
        coating.layers.append(_qw(high_index, wavelength))
        coating.layers.append(_qw(low_index, wavelength))
    coating.layers.append(_qw(high_index, wavelength))
    return coating


def design_beam_splitter(wavelength: float = 550.0, n_substrate: float = 1.5,
                         ratio: float = 0.5, high_index: str = "TiO2",
                         low_index: str = "SiO2") -> Coating:
    """
    Quarter-wave stack (HL)^p H whose normal-incidence reflectance at the
    design wavelength is closest to ``ratio``. Quarter-wave stacks give
    discrete reflectance levels, so the achieved value (``coating.name``
    carries it) generally differs from the request.
    """
    best = None
    for p in range(0, 8):
        c = design_hr_coating(wavelength, n_substrate, p, high_index, low_index)
        R = c.reflectance(wavelength)
        if best is None or abs(R - ratio) < abs(best[1] - ratio):
            best = (c, R)
    assert best is not None
    coating, R = best
    coating.name = f"Beam_Splitter_R{R:.3f}"
    return coating


def design_edge_filter(wavelength: float = 550.0, edge_type: str = "longpass",
                       n_substrate: float = 1.5, num_pairs: int = 20,
                       high_index: str = "TiO2", low_index: str = "SiO2") -> Coating:
    """
    Quarter-wave edge filter with its stop-band edge at ``wavelength``.

    The stop band of a quarter-wave stack centred at lambda0 spans
    lambda0/(1 +- dg) with dg = (2/pi) asin((nH - nL)/(nH + nL)). A
    longpass filter (0.5H L 0.5H)^p places the long-wave edge at the
    requested wavelength; a shortpass (0.5L H 0.5L)^p the short-wave edge.
    """
    nH, nL = _index(high_index, wavelength), _index(low_index, wavelength)
    dg = (2 / np.pi) * np.arcsin((nH - nL) / (nH + nL))
    if edge_type == "longpass":
        lam0 = wavelength * (1 - dg)
        unit = [(high_index, 0.5), (low_index, 1.0), (high_index, 0.5)]
    elif edge_type == "shortpass":
        lam0 = wavelength * (1 + dg)
        unit = [(low_index, 0.5), (high_index, 1.0), (low_index, 0.5)]
    else:
        raise ValueError("edge_type must be 'longpass' or 'shortpass'")
    coating = Coating(name=f"{edge_type}_filter", n_substrate=n_substrate)
    for _ in range(num_pairs):
        for mat, f in unit:
            coating.layers.append(_qw(mat, lam0, f))
    return coating


def design_bandpass_filter(center_wavelength: float = 550.0, bandwidth: float = 50.0,
                           n_substrate: float = 1.5, high_index: str = "TiO2",
                           low_index: str = "SiO2") -> Coating:
    """
    All-dielectric Fabry-Perot filter (HL)^p H 2L H (LH)^p. The number of
    mirror pairs p is chosen so the computed transmission FWHM is closest
    to ``bandwidth`` (nm); the achieved FWHM is reported in the name.
    """
    wl = np.linspace(center_wavelength * 0.7, center_wavelength * 1.3, 2001)
    best = None
    for p in range(1, 9):
        c = Coating(name="Bandpass_Filter", n_substrate=n_substrate)
        for _ in range(p):
            c.layers += [_qw(high_index, center_wavelength), _qw(low_index, center_wavelength)]
        c.layers += [_qw(high_index, center_wavelength), _qw(low_index, center_wavelength, 2.0),
                     _qw(high_index, center_wavelength)]
        for _ in range(p):
            c.layers += [_qw(low_index, center_wavelength), _qw(high_index, center_wavelength)]
        T = c.spectrum(wl)["transmittance"]
        k = int(np.argmin(abs(wl - center_wavelength)))
        half = T[k] / 2
        lo = k
        while lo > 0 and T[lo] >= half:
            lo -= 1
        hi = k
        while hi < len(wl) - 1 and T[hi] >= half:
            hi += 1
        fwhm = wl[hi] - wl[lo]
        if best is None or abs(fwhm - bandwidth) < abs(best[1] - bandwidth):
            best = (c, fwhm)
    assert best is not None
    coating, fwhm = best
    coating.name = f"Bandpass_Filter_FWHM{fwhm:.1f}nm"
    return coating
