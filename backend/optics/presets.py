"""
Preset optical systems.

Each preset is a textbook configuration whose parameters follow from
first-order optics (stated in its description). Image planes are placed at
the computed paraxial image for the analysis wavelength. Thin lenses are
ideal lenses (see :mod:`optics.raytrace`), so thin-lens presets show
first-order behaviour and colour only; the thick-lens and mirror presets
show real aberrations.
"""

import math

from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Mirror, ApertureStop,
    Object, ImagePlane, AnalysisSettings,
)
from optics.materials import get_material

_GREEN = 550e-9
_D = 587.5618e-9


def _settings(wl=_GREEN, n=11):
    return AnalysisSettings(num_rays=n, ray_types=["chief", "marginal", "fill"],
                            aperture_fraction=1.0, wavelength=wl)


def _focused(system: OpticalSystem) -> OpticalSystem:
    """Move the image plane to the paraxial image (when it is finite)."""
    from optics.raytrace import first_order
    z = first_order(system).image_z
    if math.isfinite(z):
        return system.model_copy(update={"image_plane": ImagePlane(position=z)})
    return system


def _achromat(f: float, crown: str, flint: str):
    """Thin-lens achromat powers phi1 = phi V1/(V1-V2), phi2 = -phi V2/(V1-V2)."""
    v1, v2 = get_material(crown).vd, get_material(flint).vd
    if v1 is None or v2 is None:
        raise ValueError("Both glasses need an Abbe number")
    phi = 1.0 / f
    return 1.0 / (phi * v1 / (v1 - v2)), 1.0 / (-phi * v2 / (v1 - v2))


def get_presets() -> list[dict]:
    """Return the preset systems with metadata."""
    f1, f2 = _achromat(0.100, "N-BK7", "N-SF5")
    far = 1.0e6   # object distance treated as infinity (field from height/distance)
    return [
        {
            "id": "single_lens",
            "name": "Single Thin Lens",
            "description": "f = 100 mm lens with the object at 2f: image at 2f, magnification -1.",
            "category": "Basic",
            "system": _focused(OpticalSystem(
                components=[ThinLens(id="L1", position=0.200, focal_length=0.100,
                                     aperture_diameter=0.025, material="N-BK7")],
                wavelengths=[_GREEN],
                object=Object(position=0.0, height=0.010),
                image_plane=ImagePlane(position=0.400),
                analysis_settings=_settings(),
            )),
        },
        {
            "id": "keplerian_telescope",
            "name": "Keplerian Telescope",
            "description": "Objective 200 mm and eyepiece 100 mm separated by f1 + f2 = 300 mm "
                           "(afocal, angular magnification -2); object at infinity, 0.5 deg field. "
                           "The image plane is the exit pupil region (output is collimated).",
            "category": "Telescope",
            "system": OpticalSystem(
                components=[
                    ThinLens(id="objective", position=0.0, focal_length=0.200, aperture_diameter=0.050, material="N-BK7"),
                    ThinLens(id="eyepiece", position=0.300, focal_length=0.100, aperture_diameter=0.025, material="N-BK7"),
                ],
                wavelengths=[_GREEN],
                object=Object(position=-far, height=far * math.tan(math.radians(0.5))),
                image_plane=ImagePlane(position=0.450),
                analysis_settings=_settings(),
            ),
        },
        {
            "id": "galilean_telescope",
            "name": "Galilean Telescope",
            "description": "Objective 200 mm and negative eyepiece -50 mm separated by "
                           "f1 + f2 = 150 mm (afocal, angular magnification +4); object at infinity.",
            "category": "Telescope",
            "system": OpticalSystem(
                components=[
                    ThinLens(id="objective", position=0.0, focal_length=0.200, aperture_diameter=0.050, material="N-BK7"),
                    ThinLens(id="eyepiece", position=0.150, focal_length=-0.050, aperture_diameter=0.025, material="N-SF11"),
                ],
                wavelengths=[_GREEN],
                object=Object(position=-far, height=far * math.tan(math.radians(0.25))),
                image_plane=ImagePlane(position=0.200),
                analysis_settings=_settings(),
            ),
        },
        {
            "id": "microscope",
            "name": "Compound Microscope (thin lenses)",
            "description": "20 mm objective forming a 4x intermediate image at the front focal "
                           "plane of a 50 mm eyepiece, so the output is collimated for the eye.",
            "category": "Microscope",
            "system": OpticalSystem(
                components=[
                    ThinLens(id="objective", position=0.050, focal_length=0.020, aperture_diameter=0.010, material="N-BK7"),
                    ThinLens(id="eyepiece", position=0.200, focal_length=0.050, aperture_diameter=0.015, material="N-BK7"),
                ],
                wavelengths=[_GREEN],
                object=Object(position=0.025, height=0.0005),
                image_plane=ImagePlane(position=0.300),
                analysis_settings=_settings(),
            ),
        },
        {
            "id": "beam_expander",
            "name": "Beam Expander (Keplerian, 3x)",
            "description": "50 mm and 150 mm lenses separated by f1 + f2 = 200 mm: a collimated "
                           "input beam leaves collimated and 3x wider.",
            "category": "Beam Delivery",
            "system": OpticalSystem(
                components=[
                    ThinLens(id="L1", position=0.0, focal_length=0.050, aperture_diameter=0.010, material="N-BK7"),
                    ThinLens(id="L2", position=0.200, focal_length=0.150, aperture_diameter=0.040, material="N-BK7"),
                ],
                wavelengths=[_GREEN],
                object=Object(position=-far, height=0.0),
                image_plane=ImagePlane(position=0.300),
                analysis_settings=_settings(),
            ),
        },
        {
            "id": "relay_lens",
            "name": "4f Relay",
            "description": "Two 100 mm lenses 2f apart; object at the front focal plane of L1 is "
                           "imaged 1:1 (inverted) at the back focal plane of L2.",
            "category": "Relay",
            "system": _focused(OpticalSystem(
                components=[
                    ThinLens(id="L1", position=0.0, focal_length=0.100, aperture_diameter=0.025, material="N-BK7"),
                    ThinLens(id="L2", position=0.200, focal_length=0.100, aperture_diameter=0.025, material="N-BK7"),
                ],
                wavelengths=[_GREEN],
                object=Object(position=-0.100, height=0.005),
                image_plane=ImagePlane(position=0.300),
                analysis_settings=_settings(),
            )),
        },
        {
            "id": "collimator",
            "name": "Collimator",
            "description": "Point source at the front focal point of a 100 mm lens: the output is "
                           "collimated (image at infinity).",
            "category": "Beam Delivery",
            "system": OpticalSystem(
                components=[ThinLens(id="collimator", position=0.100, focal_length=0.100,
                                     aperture_diameter=0.050, material="N-BK7")],
                wavelengths=[_GREEN],
                object=Object(position=0.0, height=0.001),
                image_plane=ImagePlane(position=0.500),
                analysis_settings=_settings(),
            ),
        },
        {
            "id": "achromat",
            "name": "Thin-Lens Achromat (N-BK7 / N-SF5)",
            "description": f"f = 100 mm achromatic doublet from the thin-lens achromat condition "
                           f"phi1/V1 + phi2/V2 = 0 with catalog Abbe numbers: f1 = {f1 * 1e3:.2f} mm "
                           f"(N-BK7), f2 = {f2 * 1e3:.2f} mm (N-SF5). F and C focus together.",
            "category": "Camera Lens",
            "system": _focused(OpticalSystem(
                components=[
                    ThinLens(id="crown", position=0.0, focal_length=f1, aperture_diameter=0.025, material="N-BK7"),
                    ThinLens(id="flint", position=0.0, focal_length=f2, aperture_diameter=0.025, material="N-SF5"),
                ],
                wavelengths=[486.1327e-9, _D, 656.2725e-9],
                object=Object(position=-far, height=far * math.tan(math.radians(1.0))),
                image_plane=ImagePlane(position=0.100),
                analysis_settings=_settings(_D, 15),
            )),
        },
        {
            "id": "thick_lens",
            "name": "Thick Biconvex Lens",
            "description": "N-BK7 lens, R1 = 100 mm, R2 = -100 mm, t = 10 mm, object 200 mm away; "
                           "shows real spherical aberration and field curvature.",
            "category": "Basic",
            "system": _focused(OpticalSystem(
                components=[ThickLens(id="TL1", position=0.200, radius1=0.100, radius2=-0.100,
                                      thickness=0.010, aperture_diameter=0.025, material="N-BK7")],
                wavelengths=[_GREEN],
                object=Object(position=0.0, height=0.005),
                image_plane=ImagePlane(position=0.400),
                analysis_settings=_settings(),
            )),
        },
        {
            "id": "parabolic_mirror",
            "name": "Parabolic Mirror Telescope (prime focus)",
            "description": "Concave paraboloid (conic -1), R = 1000 mm (f = 500 mm, f/5) with the "
                           "object at infinity: perfect on axis, coma off axis. Light reflects back "
                           "to the focus 500 mm in front of the mirror.",
            "category": "Telescope",
            "system": OpticalSystem(
                components=[Mirror(id="primary", position=0.500, width=0.100,
                                   radius=-1.0, conic=-1.0)],
                wavelengths=[_GREEN],
                object=Object(position=-far, height=far * math.tan(math.radians(0.25))),
                image_plane=ImagePlane(position=0.0),
                analysis_settings=_settings(),
            ),
        },
    ]


def get_preset_by_id(preset_id: str) -> dict | None:
    """Return a preset by its ID, or None if not found."""
    for preset in get_presets():
        if preset["id"] == preset_id:
            return preset
    return None
