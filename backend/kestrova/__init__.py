"""
Kestrova scripting API.

A small, documented layer over the optics engine for automating studies,
the equivalent of a macro language. It works the same in the in-app
console (where ``lens`` is the lens open in the editor) and in any Python
session run from the ``backend`` folder::

    import kestrova as ks

    lens = ks.sample("geiser-triplet")
    print(lens.efl * 1e3, "mm")
    for t in (0.002, 0.003, 0.004):
        trial = lens.copy().set(2, "thickness", t)
        print(t, trial.spot_rms() * 1e6, "um")
    lens.vary(0, "radius").vary(1, "radius")
    lens.optimize()
    lens.save("triplet.seq")

All values are SI (metres, radians); temperatures in degrees C. Surfaces
are 0-based, in the order of the lens data editor. Methods that change
the lens return the lens, so calls can be chained; analysis methods
return numbers or plain dicts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from optics import lens_data as _ld

__all__ = ["Lens", "open_lens", "sample", "samples", "from_dict"]


def samples() -> list[dict]:
    """The bundled reference lenses: id, name, citation."""
    from optics.reference_lenses import REFERENCE_LENSES

    return [
        {"id": r.id, "name": r.name, "citation": r.citation} for r in REFERENCE_LENSES
    ]


def sample(lens_id: str) -> "Lens":
    """A bundled reference lens by id (see samples())."""
    from optics.reference_lenses import get_reference

    ref = get_reference(lens_id)
    if ref is None:
        ids = ", ".join(s["id"] for s in samples())
        raise ValueError(f"Unknown sample {lens_id!r}; available: {ids}")
    return Lens(ref.build())


def open_lens(path: str | Path) -> "Lens":
    """Read a Code V .seq, Zemax .zmx or Kestrova .json lens file."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        return from_dict(json.loads(text))
    from optics.io.lensfile import read_lens_file

    result = read_lens_file(text, path.name)
    lens = Lens(result.lens)
    lens.warnings = list(result.warnings)
    return lens


def from_dict(data: dict) -> "Lens":
    """A lens from its JSON form (the editor's lens data)."""
    return Lens(_ld.LensData.model_validate(data))


class Lens:
    """A prescription with analysis, optimisation and file methods."""

    def __init__(self, data: _ld.LensData):
        if not isinstance(data, _ld.LensData):
            data = _ld.LensData.model_validate(data)
        self.data = data
        #: Messages from reading the lens file (unsupported features).
        self.warnings: list[str] = []

    # -- prescription --------------------------------------------------------

    def __repr__(self) -> str:
        return f"<Lens {self.data.name!r}: {len(self.data.surfaces)} surfaces>"

    def __len__(self) -> int:
        return len(self.data.surfaces)

    def __getitem__(self, i: int) -> _ld.LensSurface:
        """Surface i (an editable model: lens[2].thickness = 0.003)."""
        return self.data.surfaces[i]

    @property
    def surfaces(self) -> list[_ld.LensSurface]:
        """The surface rows (editable models)."""
        return self.data.surfaces

    @property
    def name(self) -> str:
        """The lens name."""
        return self.data.name

    def copy(self) -> "Lens":
        """An independent copy."""
        return Lens(self.data.model_copy(deep=True))

    def get(self, surface: int, parameter: str) -> float:
        """A surface parameter: radius, curvature, thickness, conic, A4..,
        decenter_x, tilt_x, ... (the editor's variable names)."""
        return _ld.get_parameter(self.data.surfaces[surface], parameter)

    def set(self, surface: int, parameter: str, value: float) -> "Lens":
        """Set a surface parameter (see get())."""
        self.data = _ld.set_parameter(self.data, surface, parameter, value)
        return self

    def set_material(self, surface: int, material: Optional[str]) -> "Lens":
        """The medium after a surface (a catalog glass, None for air)."""
        self.data.surfaces[surface].material = material
        self.data = _ld.LensData.model_validate(self.data.model_dump())
        return self

    def vary(self, surface: int, parameter: str, on: bool = True) -> "Lens":
        """Make a parameter an optimisation variable (or stop varying it)."""
        names = self.data.surfaces[surface].variables
        if on and parameter not in names:
            names.append(parameter)
        elif not on and parameter in names:
            names.remove(parameter)
        return self

    def variables(self) -> dict[str, float]:
        """The current values of the variables, keyed "<surface>.<parameter>"."""
        from optics.lens_optimize import variable_values

        return variable_values(self.data)

    def configuration(self, k: int) -> "Lens":
        """Configuration k (0-based) of a multi-configuration (zoom) lens."""
        if self.data.num_configurations <= 1:
            return self.copy()
        return Lens(_ld.configured(self.data, k))

    def resolve(self) -> "Lens":
        """Apply solves and pickups and fill automatic semi-diameters."""
        self.data = _ld.resolve(self.data)
        return self

    def system(self):
        """The engine's component-based system (for the optics modules)."""
        return _ld.to_system(self.data)

    # -- first order and image quality ---------------------------------------

    def first_order(self) -> dict:
        """Paraxial properties at the reference wavelength."""
        from optics import raytrace as rt

        fo = rt.first_order(self.system())
        return {
            "efl": fo.efl,
            "bfl": fo.bfl,
            "f_number": fo.f_number,
            "working_f_number": fo.working_f_number,
            "image_z": fo.image_z,
            "image_height": fo.image_height,
            "magnification": fo.magnification,
            "entrance_pupil_diameter": 2 * fo.entrance_pupil_semi_diameter,
            "exit_pupil_z": fo.exit_pupil_z,
            "na_image": fo.na_image,
        }

    def value(
        self, kind: str, field: Optional[int] = None, surface: Optional[int] = None
    ) -> float:
        """Any merit/constraint property: efl, bfl, working_f_number,
        magnification, total_track, center_thickness and edge_thickness
        (with ``surface``), distortion, chief_ray_angle, image_height,
        spot_rms, wavefront_rms, lateral_color, axial_color, seidel_S1..S5
        (field: 0-based field index, None for the weighted mean/edge)."""
        from types import SimpleNamespace

        from optics import raytrace as rt
        from optics.lens_optimize import constraint_value

        system = self.system()
        fo = rt.first_order(system)
        query = SimpleNamespace(kind=kind, field=field, surface=surface)
        return float(constraint_value(query, self.data, system, fo))

    @property
    def efl(self) -> float:
        """Effective focal length (m)."""
        return self.value("efl")

    @property
    def bfl(self) -> float:
        """Back focal length (m)."""
        return self.value("bfl")

    @property
    def f_number(self) -> float:
        """Paraxial F-number (EFL / entrance pupil diameter)."""
        return self.first_order()["f_number"]

    def spot_rms(self, field: Optional[int] = None) -> float:
        """Polychromatic RMS spot radius (m); None = field-weighted."""
        return self.value("spot_rms", field)

    def wavefront_rms(self, field: Optional[int] = None) -> float:
        """RMS wavefront error (waves); None = field-weighted."""
        return self.value("wavefront_rms", field)

    def fields(self) -> dict:
        """Per-field chief ray, distortion, spot and vignetting."""
        from optics.fields import field_summary

        return field_summary(self.system())

    def mtf(self, field: int = 0, frequencies: Optional[list[float]] = None) -> dict:
        """Polychromatic diffraction MTF of a field (frequencies in cycles/mm)."""
        from optics.fields import field_mtf

        return field_mtf(self.system(), field, frequencies)

    def seidel(self) -> dict:
        """Third-order (Seidel) aberrations."""
        from optics.seidel import seidel_analysis

        return seidel_analysis(self.system())

    def merit(self) -> dict:
        """The merit function report (operands, constraints, total)."""
        from optics.lens_optimize import merit_report

        return merit_report(self.data)

    # -- design --------------------------------------------------------------

    def optimize(self, max_iterations: int = 100, **kwargs: Any) -> dict:
        """Damped least squares over the variables and constraints. Updates
        the lens and returns the optimiser's report (without the lens)."""
        from optics.lens_optimize import optimize

        result = optimize(self.data, max_iterations=max_iterations, **kwargs)
        self.data = result.pop("lens")
        result.pop("system", None)
        return result

    def global_search(self, starts: int = 16, **kwargs: Any) -> list["Lens"]:
        """Multi-start global search; the distinct solutions, best first.
        The lens itself is not changed."""
        from optics.global_lens import global_optimize

        out = global_optimize(self.data, starts=starts, **kwargs)
        return [Lens(s["lens"]) for s in out.get("solutions", [])]

    def tolerance(
        self,
        tolerances: Optional[list] = None,
        trials: int = 20000,
        **kwargs: Any,
    ) -> dict:
        """Sensitivity and statistical tolerance analysis (waves RMS);
        default tolerances when none are given."""
        from optics import tolerancing as tol

        tols = (
            tolerances if tolerances is not None else tol.default_tolerances(self.data)
        )
        tols = [t if isinstance(t, tol.Tolerance) else tol.Tolerance(**t) for t in tols]
        return tol.analyze(self.data, tols, trials=trials, **kwargs).to_dict()

    def default_tolerances(self, **kwargs: Any) -> list[dict]:
        """The starting tolerance set (editable dicts)."""
        from optics import tolerancing as tol

        return [t.model_dump() for t in tol.default_tolerances(self.data, **kwargs)]

    # -- physical optics and environment -------------------------------------

    def environment(
        self,
        temperatures: list[float],
        pressure: float = 101325.0,
        mount_cte: Optional[float] = None,
    ) -> list[dict]:
        """Focus, EFL and wavefront at each temperature (deg C)."""
        from optics.environment import environment_table

        return environment_table(self.data, temperatures, pressure, mount_cte)

    def ghosts(self, field: int = 0, top: Optional[int] = 10) -> list[dict]:
        """Double-reflection ghosts, brightest first."""
        from optics.ghost_trace import ghost_analysis

        return ghost_analysis(self.system(), field, top=top)["ghosts"]

    def polarization(self, field: int = 0) -> dict:
        """Transmittance, diattenuation and retardance over the pupil."""
        from optics.polarization_trace import transmittance

        return transmittance(self.system(), field)

    def beam(
        self, waist_radius: float, waist_distance: float = 0.0, m2: float = 1.0
    ) -> dict:
        """Paraxial Gaussian beam through the lens."""
        from optics.beam_lens import beam_through

        return beam_through(self.system(), waist_radius, waist_distance, m2=m2)

    # -- files and reports ---------------------------------------------------

    def to_dict(self) -> dict:
        """The JSON form (as the editor saves it)."""
        return self.data.model_dump(mode="json")

    def save(self, path: str | Path) -> list[str]:
        """Write .seq (Code V), .zmx (Zemax) or .json; returns warnings
        for anything the format cannot hold."""
        path = Path(path)
        ext = path.suffix.lower()
        if ext == ".json":
            path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
            return []
        from optics.io.lensfile import write_codev, write_zemax

        writers = {".seq": write_codev, ".zmx": write_zemax}
        if ext not in writers:
            raise ValueError("Save as .seq, .zmx or .json")
        text, warnings = writers[ext](self.data)
        path.write_text(text, encoding="utf-8")
        return warnings

    def report(self, path: Optional[str | Path] = None, **options: Any) -> str:
        """A self-contained HTML design report (prescription, first order,
        fields, MTF, Seidel, tolerances, element drawings). Written to
        ``path`` when given; the HTML is returned either way."""
        from optics.lens_report import lens_report_html

        html = lens_report_html(self.data, **options)
        if path is not None:
            Path(path).write_text(html, encoding="utf-8")
        return html

    def drawings(self, **options: Any) -> list[dict]:
        """ISO 10110 element drawings: per element its SVG and data table."""
        from optics.io.element_drawing import element_drawings

        return element_drawings(self.data, **options)
