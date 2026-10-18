"""
Thermal analysis: focus and image quality versus temperature.

At temperature T (C), relative to the 20 C design:

- every glass index changes by the Schott dn/dT formula (vendor constants);
- every lens grows with its glass CTE: radii, centre thickness and (for a
  thin lens) the focal length scale by (1 + alpha dT), and a thin lens's
  focal length also scales by (n - 1)/(n + dn - 1);
- optionally, the mount (lens spacings and the image-plane distance) expands
  with a housing CTE ``mount_cte`` (1e-6/K) about the first element.

Materials without published thermal constants raise ValueError rather than
being treated as athermal. The air index change is not modelled.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..models import OpticalSystem, ThinLens, ThickLens, ImagePlane
from .. import raytrace as rt
from .material import get_thermal_properties, index_change

REFERENCE_TEMPERATURE = 20.0


@dataclass
class ThermalResult:
    """Result at one temperature."""
    temperature: float
    focal_shift: float          # paraxial image shift along the travel (m)
    efl_change: float           # change in effective focal length (m)
    rms_spot_radius: float      # real-ray RMS spot at the (moved) image plane (m)
    wavefront_error: float      # RMS wavefront error at that plane (m)
    focus_tolerance: float      # quarter-wave depth of focus, +-2 lambda N^2 (m)
    is_athermal: bool           # |focal_shift| within the focus tolerance


def _glasses(system: OpticalSystem) -> set:
    return {c.material for c in system.components
            if isinstance(c, (ThinLens, ThickLens)) and c.material}


def thermal_system(system: OpticalSystem, temperature: float,
                   mount_cte: Optional[float] = None):
    """
    The system at ``temperature`` and the index offsets of its glasses.

    Returns (system, index_offsets) for use with ``raytrace.build_sequence``.
    """
    dT = temperature - REFERENCE_TEMPERATURE
    wl = system.analysis_settings.wavelength
    offsets = {}
    for g in _glasses(system):
        offsets[g] = index_change(g, wl, temperature, REFERENCE_TEMPERATURE)
    comps = []
    z0 = min(c.position for c in system.components)
    grow = (lambda z: z0 + (z - z0) * (1.0 + mount_cte * 1e-6 * dT)) if mount_cte else (lambda z: z)
    for c in system.components:
        upd = {"position": grow(c.position)}
        if isinstance(c, (ThinLens, ThickLens)):
            props = get_thermal_properties(c.material)
            if props is None or props.CTE is None:
                raise ValueError(f"No published CTE for '{c.material}'")
            k = 1.0 + props.CTE * 1e-6 * dT
            if isinstance(c, ThickLens):
                upd.update(radius1=c.radius1 * k, radius2=c.radius2 * k, thickness=c.thickness * k,
                           aperture_diameter=c.aperture_diameter * k)
            else:
                from ..materials import refractive_index
                n = refractive_index(c.material, wl)
                upd.update(focal_length=c.focal_length * k * (n - 1.0) / (n + offsets[c.material] - 1.0))
        comps.append(c.model_copy(update=upd))
    img = ImagePlane(position=grow(system.image_plane.position))
    hot = system.model_copy(update={"components": comps, "image_plane": img})
    # Thin-lens focal lengths already include the index change.
    thick_offsets = {g: dn for g, dn in offsets.items()
                     if any(isinstance(c, ThickLens) and c.material == g for c in system.components)}
    return hot, thick_offsets


class ThermalAnalyzer:
    """Analyzes thermal effects on an optical system."""

    def __init__(self, system: OpticalSystem, mount_cte: Optional[float] = None):
        self.system = system
        self.mount_cte = mount_cte
        self.base_temp = REFERENCE_TEMPERATURE
        seq = rt.build_sequence(system)
        self._fo0 = rt.first_order(system, seq=seq)
        self._dir = seq.image_direction

    def analyze_at_temperature(self, temperature: float) -> ThermalResult:
        hot, offsets = thermal_system(self.system, temperature, self.mount_cte)
        seq = rt.build_sequence(hot, index_offsets=offsets)
        fo = rt.first_order(hot, seq=seq)
        shift = (fo.image_z - self._fo0.image_z) * self._dir
        px, py = rt.pupil_grid(4, "hexapolar")
        b, _, _ = rt.trace_field_rays(hot, 0.0, 0.0, px, py, seq=seq, fo=fo)
        P = rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)[0][b.valid]
        rms = float(np.sqrt(np.mean(np.sum((P[:, :2] - P[:, :2].mean(0)) ** 2, 1)))) if len(P) else float("nan")
        W, ok, _ = rt.opd(hot, 0.0, 0.0, px, py, seq=seq, fo=fo)
        w = W[ok]
        wfe = float(np.sqrt(np.mean((w - w.mean()) ** 2))) if w.size else float("nan")
        lam = self.system.analysis_settings.wavelength
        N = fo.working_f_number
        tol = 2.0 * lam * N * N
        return ThermalResult(
            temperature=temperature, focal_shift=shift,
            efl_change=fo.efl - self._fo0.efl, rms_spot_radius=rms,
            wavefront_error=wfe, focus_tolerance=tol, is_athermal=abs(shift) <= tol,
        )

    def temperature_sweep(self, temp_range: tuple = (-40, 80), num_points: int = 13) -> list:
        return [self.analyze_at_temperature(float(T))
                for T in np.linspace(temp_range[0], temp_range[1], num_points)]


def thermal_defocus(system: OpticalSystem, temperature: float, base_temp: float = 20.0,
                    mount_cte: Optional[float] = None) -> float:
    """Paraxial image shift (m, along the travel) at ``temperature``."""
    if base_temp != REFERENCE_TEMPERATURE:
        raise ValueError("Catalog thermal constants are referenced to 20 C")
    return ThermalAnalyzer(system, mount_cte).analyze_at_temperature(temperature).focal_shift


def athermalization_check(system: OpticalSystem, temp_range: tuple = (-40, 80),
                          tolerance: Optional[float] = None,
                          mount_cte: Optional[float] = None) -> bool:
    """
    True when the focus shift stays within ``tolerance`` (default: the
    quarter-wave depth of focus +-2 lambda N^2) across the range.
    """
    results = ThermalAnalyzer(system, mount_cte).temperature_sweep(temp_range, num_points=5)
    return all(abs(r.focal_shift) <= (tolerance if tolerance is not None else r.focus_tolerance)
               for r in results)


def temperature_sweep(system: OpticalSystem, temp_range: tuple = (-40, 80),
                      num_points: int = 13, mount_cte: Optional[float] = None) -> list:
    """Focus shift, EFL change, spot and wavefront error versus temperature."""
    return [
        {
            "temperature": r.temperature,
            "focal_shift": r.focal_shift,
            "efl_change": r.efl_change,
            "rms_spot": r.rms_spot_radius,
            "wavefront_error_rms": r.wavefront_error,
            "focus_tolerance": r.focus_tolerance,
            "is_athermal": r.is_athermal,
        }
        for r in ThermalAnalyzer(system, mount_cte).temperature_sweep(temp_range, num_points)
    ]
