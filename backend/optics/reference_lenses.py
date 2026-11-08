"""
Reference lenses: published designs with published results.

Each entry reproduces a prescription exactly as its source prints it (in
millimetres; converted to metres here) together with the numbers the source
reports for it. ``tests/test_reference_lenses.py`` checks the engine against
those numbers, and the app offers the lenses as samples.

The published numbers come from three kinds of source, and the tests hold
each to a tolerance that matches what the source can support:

- an independent program's printed output for the same prescription
  (ray-optics, M. Hayford, https://github.com/mjhoptics/ray-optics):
  first-order data, paraxial ray heights, Seidel sums and exact real rays,
  quoted to 4-6 significant figures;
- a designer's or textbook's stated focal length and aperture, quoted for
  the original glasses (the copy used here substitutes catalogue
  equivalents, so these hold to about 1 %);
- a published instrument specification (the Hubble Space Telescope).

Where a source printed a value without its sign or as a blank (an
infinite radius), the sign or infinity filled in here is stated in the
entry's ``notes`` and confirmed by the published focal length.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from .lens_data import LensData, LensSurface, SurfaceType
from .materials import model_glass_name
from .models import AnalysisSettings, FieldPoint

MM = 1e-3
F_LINE, D_LINE, C_LINE = 486.1327e-9, 587.5618e-9, 656.2725e-9


@dataclass(frozen=True)
class ReferenceLens:
    """A published lens and what its source reports about it."""

    id: str
    name: str
    description: str
    citation: str
    url: str
    build: Callable[[], LensData]
    #: Published scalar results (lengths in mm, angles in degrees).
    published: dict = field(default_factory=dict)
    #: Larger published tables (paraxial rays, Seidel rows, real rays).
    tables: dict = field(default_factory=dict)
    notes: str = ""


def _row(
    radius: float,
    thickness: float,
    material: Optional[str] = None,
    semi: Optional[float] = None,
    *,
    label: str = "",
    stop: bool = False,
    conic: float = 0.0,
    even: tuple = (),
    odd: tuple = (),
) -> LensSurface:
    """One surface in millimetres (radius 0 = flat). ``even`` holds the r^4,
    r^6, ... coefficients and ``odd`` the r^3, r^5, ... coefficients, in mm
    units (a coefficient of r^k has units mm^(1-k))."""
    kind: SurfaceType = (
        "odd_asphere" if odd else ("even_asphere" if even else "standard")
    )
    return LensSurface(
        label=label,
        surface_type=kind,
        radius=radius * MM,
        thickness=thickness * MM,
        material=material,
        semi_diameter=None if semi is None else semi * MM,
        is_stop=stop,
        conic=conic,
        aspheric_coefficients=[
            a * MM ** (1 - k) for k, a in zip(range(4, 22, 2), even)
        ],
        odd_coefficients=[b * MM ** (1 - k) for k, b in zip(range(3, 21, 2), odd)],
    )


def _lens(
    name: str,
    rows: list[LensSurface],
    *,
    field_deg: float,
    relative_fields: tuple = (0.0, 0.7071, 1.0),
    wavelengths: tuple = (F_LINE, D_LINE, C_LINE),
    reference: float = D_LINE,
    weights: Optional[tuple] = None,
    epd: Optional[float] = None,
) -> LensData:
    """A lens with its object at infinity and a field given as an angle."""
    angle = math.radians(field_deg)
    return LensData(
        name=name,
        surfaces=rows,
        object_distance=None,
        field_angle=angle,
        fields=[FieldPoint(y=math.atan(f * math.tan(angle))) for f in relative_fields],
        field_type="angle",
        entrance_pupil_diameter=None if epd is None else epd * MM,
        wavelengths=list(wavelengths),
        wavelength_weights=None if weights is None else list(weights),
        analysis_settings=AnalysisSettings(wavelength=reference),
    )


# =============================================================================
# Geiser triplet (Sasian, OPTI 517) as listed by ray-optics
# =============================================================================


def _sasian_triplet() -> LensData:
    return _lens(
        "Geiser triplet (Sasian OPTI 517)",
        [
            _row(23.713, 4.831, "N-LAK9", 10.009),
            _row(7331.288, 5.86, None, 8.9482),
            _row(-24.456, 0.975, "N-SF5", 4.7919, stop=True),
            _row(21.896, 4.822, None, 4.7761),
            _row(86.759, 3.127, "N-LAK9", 8.0217),
            _row(-20.4942, 41.2365, None, 8.3321),
        ],
        field_deg=20.0,
        weights=(0.5, 1.0, 0.5),
        epd=12.5,
    )


SASIAN_TRIPLET = ReferenceLens(
    id="geiser-triplet",
    name="Geiser triplet, f/4, 50 mm",
    description="Air-spaced Cooke triplet, f/4, ±20° field (N-LAK9 / N-SF5).",
    citation=(
        "Triplet attributed to Geiser, used in J. Sasian, Lens Design OPTI 517, "
        "Univ. of Arizona; prescription and results from the ray-optics "
        "'Triplet example' (M. Hayford)."
    ),
    url="https://ray-optics.readthedocs.io/en/latest/examples/SasianTriplet/SasianTriplet.html",
    build=_sasian_triplet,
    published={
        "efl": 50.0,
        "ffl": -37.1,
        "bfl": 41.24,
        "f_number": 4.0,
        "entrance_pupil_from_first": 11.68,
        "exit_pupil_from_last": -10.01,
        "exit_pupil_semi": 6.406,
        "image_height": 18.2,
        "n_d": {"N-LAK9": 1.69100, "N-SF5": 1.67271},
    },
    tables={
        # Paraxial marginal and chief ray heights (mm) at surfaces 1-6 and the
        # image, at 587.5618 nm, and the final slopes.
        "marginal_height": [
            6.25,
            5.72969,
            4.66559,
            4.63455,
            5.06436,
            5.1546,
            0.000143648,
        ],
        "chief_height": [
            -4.25088,
            -2.85718,
            3.53405e-07,
            0.2842,
            2.67738,
            3.55571,
            18.1985,
        ],
        "marginal_slope_image": -0.124998,
        "chief_slope_object": 0.36397,
        # Seidel S-I .. S-V per surface (mm), rows = surfaces 1-6, then the sum.
        "seidel": [
            [0.027654, 0.019379, 0.013581, 0.089174, 0.072010],
            [0.022082, -0.059501, 0.160327, -0.000288, -0.431229],
            [-0.105156, 0.137692, -0.180295, -0.085097, 0.347506],
            [-0.045358, -0.076796, -0.130024, -0.095046, -0.381069],
            [0.007942, 0.028382, 0.101431, 0.024373, 0.449596],
            [0.103810, -0.050068, 0.024148, 0.103180, -0.061411],
        ],
        "seidel_sum": [0.010973, -0.000912, -0.010832, 0.036297, -0.004597],
        # Wavefront coefficients in waves at 587.5618 nm.
        "wavefront_waves": {
            "W040": 2.334457,
            "W131": -0.776108,
            "W222": -9.218154,
            "W220": 10.834770,
            "W311": -3.911650,
        },
    },
)


# =============================================================================
# Cell-phone camera lens, US 7,535,658, as modelled by ray-optics
# =============================================================================

# ray-optics RadialPolynomial terms a1 .. a10 (r^1 .. r^10, mm) and its conic
# asphere ec (conic constant = ec - 1), as entered in the ray-optics example.
_PHONE_SURFACES = [
    # radius, thickness, n_d, V_d, ec, a1..a10
    (
        1.962,
        1.19,
        1.471,
        76.6,
        2.153,
        [
            0,
            0,
            -1.895e-2,
            2.426e-2,
            -5.123e-2,
            8.371e-4,
            7.850e-3,
            4.091e-3,
            -7.732e-3,
            -4.265e-3,
        ],
    ),
    (
        33.398,
        0.93,
        None,
        None,
        40.18,
        [
            0,
            0,
            -4.966e-3,
            -1.434e-2,
            -6.139e-3,
            -9.284e-5,
            6.438e-3,
            -5.72e-3,
            -2.385e-2,
            1.108e-2,
        ],
    ),
    (
        -2.182,
        0.75,
        1.603,
        27.5,
        2.105,
        [
            0,
            0,
            -4.388e-2,
            -2.555e-2,
            5.16e-2,
            -4.307e-2,
            -2.831e-2,
            3.162e-2,
            4.630e-2,
            -4.877e-2,
        ],
    ),
    (
        -6.367,
        0.1,
        None,
        None,
        3.382,
        [
            0,
            0,
            -1.131e-1,
            -7.863e-2,
            1.094e-1,
            6.228e-3,
            -2.216e-2,
            -5.89e-3,
            4.123e-3,
            1.041e-3,
        ],
    ),
    (
        5.694,
        0.89,
        1.510,
        56.2,
        -221.1,
        [
            0,
            0,
            -7.876e-2,
            7.02e-2,
            1.575e-3,
            -9.958e-3,
            -7.322e-3,
            6.914e-4,
            2.54e-3,
            -7.65e-4,
        ],
    ),
    (
        9.192,
        0.16,
        None,
        None,
        0.9331,
        [
            0,
            0,
            9.694e-3,
            -2.516e-3,
            -3.606e-3,
            -2.497e-4,
            -6.84e-4,
            -1.414e-4,
            2.932e-4,
            -7.284e-5,
        ],
    ),
    (
        1.674,
        0.85,
        1.510,
        56.2,
        -7.617,
        [
            0,
            0,
            7.429e-2,
            -6.933e-2,
            -5.811e-3,
            2.396e-3,
            2.100e-3,
            -3.119e-4,
            -5.552e-5,
            7.969e-6,
        ],
    ),
    (
        1.509,
        0.70,
        None,
        None,
        -2.707,
        [
            0,
            0,
            1.767e-3,
            -4.652e-2,
            1.625e-2,
            -3.522e-3,
            -7.106e-4,
            3.825e-4,
            6.271e-5,
            -2.631e-5,
        ],
    ),
]


def _phone_lens() -> LensData:
    rows = [_row(0.0, 0.0, None, 0.79358, label="STO", stop=True)]
    for r, t, nd, vd, ec, a in _PHONE_SURFACES:
        glass = None if nd is None or vd is None else model_glass_name(nd, vd)
        rows.append(
            _row(r, t, glass, conic=ec - 1.0, odd=tuple(a[2::2]), even=tuple(a[3::2]))
        )
    rows.append(_row(0.0, 0.40, model_glass_name(1.516, 64.1), label="Filter"))
    rows.append(_row(0.0, 0.64, None))
    lens = _lens(
        "Cell-phone camera lens (US 7,535,658)",
        rows,
        field_deg=31.76,
        weights=(0.5, 1.0, 0.5),
    )
    return lens


PHONE_LENS = ReferenceLens(
    id="phone-camera-us7535658",
    name="Cell-phone camera lens, f/3.5, 5.6 mm",
    description=(
        "Four plastic/glass aspheric elements with odd and even polynomial "
        "terms and an IR filter (US Patent 7,535,658)."
    ),
    citation=(
        "U.S. Patent 7,535,658; prescription and exact ray traces from the "
        "ray-optics 'Cell Phone Camera Lens' example (M. Hayford)."
    ),
    url="https://ray-optics.readthedocs.io/en/latest/examples/Cell_Phone_lens/Cell_Phone_lens.html",
    build=_phone_lens,
    notes=(
        "Aspheric terms and conics are entered as in the ray-optics model "
        "(conic constant = ec - 1). The field angle is the 31.76° that "
        "ray-optics reports for its 3.5 mm image-height field."
    ),
    published={
        "efl": 5.555,
        "ffl": -7.531,
        "bfl": 0.5678,
        "exit_pupil_from_last": -3.602,
        "exit_pupil_semi": 0.5854,
        "entrance_pupil_semi": 0.7936,
    },
    tables={
        # Exact rays at 587.5618 nm (n = n_d). Each row: X, Y, Z (local, mm;
        # Z is the sag at the intersection) and the direction cosines L, M, N
        # after the surface; rows run over the stop, the 8 lens surfaces, the
        # 2 filter faces and the image.
        "marginal_ray": {
            "start": [0.0, 1.0, 0.0],
            "direction": [0.0, 0.0, 1.0],
            "rows": [
                [0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                [0.0, 1.0, 0.26119, 0.0, -0.163284, 0.986579],
                [0.0, 0.84711, -0.0050525, 0.0, -0.272278, 0.962219],
                [0.0, 0.61108, -0.10094, 0.0, -0.024063, 0.999710],
                [0.0, 0.59188, -0.053212, 0.0, -0.171810, 0.985130],
                [0.0, 0.56295, 0.012694, 0.0, -0.122925, 0.992416],
                [0.0, 0.45281, 0.01188, 0.0, -0.158261, 0.987397],
                [0.0, 0.42089, 0.051033, 0.0, -0.178956, 0.983857],
                [0.0, 0.27126, 0.023675, 0.0, -0.185004, 0.982738],
                [0.0, 0.14394, 0.0, 0.0, -0.122034, 0.992526],
                [0.0, 0.09476, 0.0, 0.0, -0.185004, 0.982738],
                [0.0, -0.02573, 0.0, 0.0, -0.185004, 0.982738],
            ],
        },
        "skew_ray": {
            "start": [-0.08601351, -0.17302717, 0.0],
            "direction": [0.08601351, 0.17302717, 0.98115405],
            "rows": [
                [-0.08601, -0.17303, 0.0, 0.086014, 0.173027, 0.981154],
                [-0.08520, -0.17139, 0.009271, 0.072254, 0.145349, 0.986739],
                [0.00126, 0.00253, 1.1955e-07, 0.106304, 0.213844, 0.971066],
                [0.10169, 0.20456, -0.012595, 0.085295, 0.171581, 0.981471],
                [0.16643, 0.33479, -0.017664, 0.106581, 0.214401, 0.970913],
                [0.18026, 0.36261, 0.0083478, 0.066253, 0.133277, 0.988862],
                [0.24047, 0.48374, 0.017019, 0.115071, 0.231480, 0.966010],
                [0.26910, 0.54133, 0.097372, 0.032613, 0.065605, 0.997313],
                [0.29782, 0.59910, 0.1256, 0.126731, 0.254936, 0.958617],
                [0.37376, 0.75186, 0.0, 0.083596, 0.168164, 0.982208],
                [0.40780, 0.82034, 0.0, 0.126731, 0.254936, 0.958617],
                [0.49241, 0.99054, 0.0, 0.126731, 0.254936, 0.958617],
            ],
        },
        # Chief ray of the 0.7071 field, through the centre of the stop.
        "chief_ray_field_1": {
            "start": [0.0, 0.0, 0.0],
            "direction": [0.0, 0.382041, 0.924145],
            "rows": [
                [0.0, 0.0, 0.0, 0.0, 0.382041, 0.924145],
                [0.0, 0.0, 2.4226e-14, 0.0, 0.259715, 0.965685],
                [0.0, 0.32037, 0.0012037, 0.0, 0.384968, 0.922930],
                [0.0, 0.65813, -0.11903, 0.0, 0.381160, 0.924509],
                [0.0, 0.95032, -0.16032, 0.0, 0.400332, 0.916370],
                [0.0, 1.07549, 0.026181, 0.0, 0.257929, 0.966164],
                [0.0, 1.33050, 0.091422, 0.0, 0.441538, 0.897243],
                [0.0, 1.49987, 0.27561, 0.0, 0.300087, 0.953912],
                [0.0, 1.80052, 0.38131, 0.0, 0.428907, 0.903348],
                [0.0, 1.95184, 0.0, 0.0, 0.282920, 0.959143],
                [0.0, 2.06983, 0.0, 0.0, 0.428907, 0.903348],
                [0.0, 2.37370, 0.0, 0.0, 0.428907, 0.903348],
            ],
        },
    },
)


# =============================================================================
# Double Gauss, Lautenbacher & Brendel (US 2,784,643), via Smith
# =============================================================================


def _double_gauss() -> LensData:
    return _lens(
        "Double Gauss f/1.7 (US 2,784,643)",
        [
            _row(75.050, 9.000, "S-LAM3", 33.0),
            _row(270.700, 0.100, None, 33.0),
            _row(39.270, 16.510, "S-BAH11", 27.5),
            _row(0.0, 2.000, "N-SF5", 24.5),
            _row(25.650, 10.990, None, 19.5),
            _row(0.0, 13.000, None, 18.6, label="STO", stop=True),
            _row(-31.870, 7.030, "N-SF5", 18.5),
            _row(0.0, 8.980, "S-LAM3", 21.0),
            _row(-43.510, 0.100, None, 21.0),
            _row(221.140, 7.980, "S-BAH11", 23.0),
            _row(-88.790, 61.418, None, 23.0),
        ],
        field_deg=9.5,
        wavelengths=(550e-9,),
        reference=550e-9,
        epd=58.941,
    )


DOUBLE_GAUSS = ReferenceLens(
    id="double-gauss-us2784643",
    name="Double Gauss, f/1.7, 100 mm",
    description="Six-element double Gauss, f/1.7, 19° field of view.",
    citation=(
        "Lautenbacher & Brendel (Agfa), U.S. Patent 2,784,643, from W. J. Smith, "
        "Modern Lens Design, 2nd ed. (2005), p. 323, as tabulated in the "
        "COMSOL 'Double Gauss Lens' model (glasses replaced by S-LAM3, "
        "S-BAH11 and N-SF5)."
    ),
    url="https://doc.comsol.com/6.3/doc/com.comsol.help.models.roptics.double_gauss_lens/models.roptics.double_gauss_lens.pdf",
    build=_double_gauss,
    notes=(
        "The tabulated radii lost their signs and infinities in the source "
        "text; they are filled in as the classical double Gauss form "
        "(+, +, +, flat, + | stop | -, flat, -, +, -), which reproduces the "
        "published focal length."
    ),
    published={
        "efl": 100.2,
        "f_number": 1.7,
        "image_distance": 61.418,
        # Best (minimum RMS) focus on axis at 550 nm, measured from the
        # nominal image plane (negative = towards the lens).
        "best_focus_shift": -0.180,
    },
)


# =============================================================================
# Field-flattened Petzval (Kidger, Fundamental Optical Design)
# =============================================================================


def _petzval() -> LensData:
    return _lens(
        "Field-flattened Petzval (Kidger)",
        [
            _row(98.45049, 13.0, "N-BK7", 28.478),
            _row(-83.29386, 4.0, "N-KZFS5", 26.267),
            _row(-1421.38828, 40.0, None, 22.020),
            _row(0.0, 40.0, None, 16.631, label="STO", stop=True),
            _row(59.00613, 12.0, "N-SK2", 20.543),
            _row(-54.36470, 3.0, "N-SF5", 20.074),
            _row(-549.36547, 46.82210, None, 16.492),
            _row(-39.80076, 2.0, "N-SF5", 17.297),
            _row(0.0, 1.9548, None, 18.940),
        ],
        field_deg=9.0,
        relative_fields=(0.0, 6.0 / 9.0, 1.0),
        wavelengths=(475e-9, 550e-9, 625e-9),
        reference=550e-9,
        epd=41.5,
    )


PETZVAL = ReferenceLens(
    id="petzval-kidger",
    name="Field-flattened Petzval, f/2.4, 100 mm",
    description="Two cemented doublets with a field flattener near the image.",
    citation=(
        "M. J. Kidger, Fundamental Optical Design (SPIE, 2001), p. 191, as "
        "tabulated in the COMSOL 'Petzval Lens' model (some glasses replaced "
        "by catalogue equivalents, back focus adjusted)."
    ),
    url="https://doc.comsol.com/6.4/doc/com.comsol.help.models.roptics.petzval_lens/models.roptics.petzval_lens.pdf",
    build=_petzval,
    published={"efl": 100.0, "f_number": 2.4},
)


# =============================================================================
# Hubble Space Telescope (nominal Ritchey-Chretien design)
# =============================================================================


def _hubble() -> LensData:
    arcmin = 1.0 / 60.0
    return _lens(
        "Hubble Space Telescope OTA",
        [
            _row(
                -11040.0,
                -4906.071,
                "MIRROR",
                1200.0,
                label="Primary",
                stop=True,
                conic=-1.0022985,
            ),
            _row(
                -1358.0,
                4906.071 + 1500.0,
                "MIRROR",
                197.5,
                label="Secondary",
                conic=-1.496,
            ),
        ],
        field_deg=10 * arcmin,
        relative_fields=(0.0, 0.5, 1.0),
        wavelengths=(550e-9,),
        reference=550e-9,
    )


HUBBLE = ReferenceLens(
    id="hubble-ota",
    name="Hubble Space Telescope, f/24, 57.6 m",
    description=(
        "Ritchey-Chrétien Cassegrain: 2.4 m hyperbolic primary and hyperbolic "
        "secondary (nominal pre-launch figures)."
    ),
    citation=(
        "Mirror radii, conics and spacings from the COMSOL 'Hubble Space "
        "Telescope' model (nominal design); 57.6 m focal length and f/24 from "
        "the STScI HST Primer, Optical Telescope Assembly."
    ),
    url="https://doc.comsol.com/6.1/doc/com.comsol.help.models.roptics.hubble_space_telescope/models.roptics.hubble_space_telescope.pdf",
    build=_hubble,
    notes=(
        "Signs follow the sequential convention: both mirrors have negative "
        "radii and the primary-to-secondary distance is negative. The image "
        "is 1500 mm behind the primary vertex. The 600 mm central hole of "
        "the primary is not modelled (it does not change first-order data)."
    ),
    published={"efl": 57600.0, "f_number": 24.0, "epd": 2400.0},
)


REFERENCE_LENSES: tuple[ReferenceLens, ...] = (
    SASIAN_TRIPLET,
    DOUBLE_GAUSS,
    PETZVAL,
    PHONE_LENS,
    HUBBLE,
)


def get_reference(lens_id: str) -> Optional[ReferenceLens]:
    return next((r for r in REFERENCE_LENSES if r.id == lens_id), None)
