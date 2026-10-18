"""
Radiometry, photometry, and BRDF models.

Adds the energy-domain analyses that were missing:

    - Radiometric quantities: radiance, irradiance, radiant flux, etendue
    - Photometric quantities: luminous flux, illuminance, efficacy
    - CIE 1931 photopic luminosity function (Wyman multi-lobe fit)
    - Blackbody spectral radiance (Planck)
    - BRDF models (Lambertian, Harvey-Shack/ABg) plus a few illustrative
      surface-finish models defined from an assumed total integrated scatter
      (not measured data)

Conventions
-----------
Radiometric quantities use W and m. Photometric quantities use lm and lx.
Wavelengths are in meters unless a function name says otherwise.

All formulas are the standard definitions (see Boyd, "Radiometry and the
Detection of Optical Radiation", and Wolfe, "Introduction to Radiometry").
"""

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# Physical constants
H_PLANCK = 6.62607015e-34      # J s
C_LIGHT = 2.99792458e8          # m / s
K_BOLTZMANN = 1.380649e-23      # J / K

# Maximum luminous efficacy: the photopic peak is defined as 683 lm/W.
MAX_LUMINOUS_EFFICACY = 683.0   # lm / W

# Domain over which CIE 1931 defines the photopic luminosity function.
VISIBLE_MIN_NM = 360.0
VISIBLE_MAX_NM = 830.0


# =============================================================================
# Photopic luminosity function
# =============================================================================

def _piecewise_gaussian(x: float, mu: float, sigma_lo: float, sigma_hi: float) -> float:
    """
    Asymmetric Gaussian used by the Wyman/Sloan/Shirley colour fits.

    The width differs on either side of the peak, which is what lets a
    handful of terms reproduce the skewed CIE lobes.
    """
    sigma = sigma_lo if x < mu else sigma_hi
    t = (x - mu) / sigma
    return math.exp(-0.5 * t * t)


def photopic_luminosity(wavelength_nm: float) -> float:
    """
    CIE 1931 photopic luminosity function V(lambda), peak normalised to 1.0.

    Uses the Wyman/Sloan/Shirley (JCGT 2013) two-lobe fit to the CIE 1931
    y-bar colour matching function, which is by definition the photopic
    luminosity function. Peak value is 0.998 at 555 nm; against the CIE
    table it is within about 0.005 absolute (0.5 % of the peak) from 450 to
    700 nm, with larger relative error in the weak blue and red tails.

    Args:
        wavelength_nm: Wavelength in nanometres.

    Returns:
        Relative luminous efficiency (0 to 1).
    """
    # CIE 1931 defines V(lambda) over 360-830 nm. Outside that range the
    # Gaussian fit leaves a small spurious tail (about 1e-4 of peak at
    # 300 nm), so the domain is clamped rather than trusting the fit there.
    if wavelength_nm < VISIBLE_MIN_NM or wavelength_nm > VISIBLE_MAX_NM:
        return 0.0
    term1 = 0.821 * _piecewise_gaussian(wavelength_nm, 568.8, 46.9, 40.5)
    term2 = 0.286 * _piecewise_gaussian(wavelength_nm, 530.9, 16.3, 31.1)
    return max(0.0, min(1.0, term1 + term2))


def luminous_efficacy(wavelength: float) -> float:
    """
    Luminous efficacy of monochromatic radiation (lm/W).

    Args:
        wavelength: Wavelength in meters.

    Returns:
        Efficacy in lumens per watt (0 to 683).
    """
    v = photopic_luminosity(wavelength * 1e9)
    return MAX_LUMINOUS_EFFICACY * v


def radiant_to_luminous(power_watts: float, wavelength: float) -> float:
    """Convert monochromatic radiant power (W) to luminous flux (lm)."""
    return power_watts * luminous_efficacy(wavelength)


def luminous_to_radiant(flux_lumens: float, wavelength: float) -> float:
    """Convert luminous flux (lm) to monochromatic radiant power (W)."""
    eff = luminous_efficacy(wavelength)
    if eff <= 0.0:
        return 0.0
    return flux_lumens / eff


def photon_energy(wavelength: float) -> float:
    """Energy of a single photon (joules)."""
    if wavelength <= 0:
        return 0.0
    return H_PLANCK * C_LIGHT / wavelength


def photon_flux(power_watts: float, wavelength: float) -> float:
    """Photons per second for a given monochromatic radiant power."""
    e = photon_energy(wavelength)
    if e <= 0:
        return 0.0
    return power_watts / e


# =============================================================================
# Geometric radiometry
# =============================================================================

def solid_angle_cone(half_angle: float) -> float:
    """
    Solid angle (sr) of a right circular cone with the given half-angle.

    Omega = 2 pi (1 - cos(theta))
    """
    return 2.0 * math.pi * (1.0 - math.cos(half_angle))


def solid_angle_from_f_number(f_number: float) -> float:
    """
    Solid angle (sr) of the image-space cone of a working f-number N.

    With N = 1 / (2 n' sin U') (in air), the cone half-angle is
    U' = asin(1 / (2N)) and Omega = 2 pi (1 - cos U').

    Args:
        f_number: The working f-number N (dimensionless).
    """
    if f_number <= 0:
        return 0.0
    s = 1.0 / (2.0 * f_number)
    if s > 1.0:
        raise ValueError("A working f-number below 0.5 is not physical in air")
    return solid_angle_cone(math.asin(s))


def f_number_from_numerical_aperture(na: float, n_medium: float = 1.0) -> float:
    """Working f-number N = 1 / (2 NA). NA = n sin U already contains the
    medium index, so ``n_medium`` does not enter (kept for compatibility)."""
    if na <= 0:
        return float("inf")
    return 1.0 / (2.0 * na)


def numerical_aperture_from_f_number(f_number: float, n_medium: float = 1.0) -> float:
    """NA = 1 / (2 N) of a working f-number (``n_medium`` unused)."""
    if f_number <= 0 or not math.isfinite(f_number):
        return 0.0
    return 1.0 / (2.0 * f_number)


def etendue(area: float, solid_angle: float) -> float:
    """
    Etendue (throughput) of a beam in air, G = A * Omega_p (m^2 sr).

    G is conserved through an ideal lossless system, which is why it sets
    the fundamental limit on irradiance concentration.

    Args:
        area: Cross-sectional area (m^2).
        solid_angle: Projected solid angle of the beam (sr); for a cone of
            half-angle U it is pi sin^2 U (the plain solid angle is only its
            small-angle approximation).
    """
    return area * solid_angle


def etendue_from_f_number(area: float, f_number: float) -> float:
    """Etendue A * pi sin^2 U of an area and a working f-number cone."""
    if f_number <= 0:
        return 0.0
    return etendue(area, math.pi / (4.0 * f_number * f_number))


def irradiance_from_flux(radiant_flux: float, area: float) -> float:
    """
    Irradiance E = Phi / A (W / m^2).

    Args:
        radiant_flux: Radiant power (W).
        area: Receiving area (m^2).
    """
    if area <= 0:
        return 0.0
    return radiant_flux / area


def illuminance_from_flux(luminous_flux: float, area: float) -> float:
    """Illuminance E = Phi_v / A (lux = lm / m^2)."""
    if area <= 0:
        return 0.0
    return luminous_flux / area


def radiance_from_irradiance(irradiance: float, solid_angle: float) -> float:
    """
    Radiance L = E / Omega (W / (m^2 sr)).

    For a Lambertian emitter, L = M / pi where M is the exitance.
    """
    if solid_angle <= 0:
        return 0.0
    return irradiance / solid_angle


def lambertian_intensity_to_radiance(intensity: float, area: float) -> float:
    """Convert a Lambertian intensity (W/sr) to radiance (W/(m^2 sr))."""
    if area <= 0:
        return 0.0
    return intensity / area


def image_irradiance_from_object(
    object_radiance: float,
    f_number: float,
    transmission: float = 1.0,
    n_image: float = 1.0,
) -> float:
    """
    On-axis image irradiance from an extended Lambertian object.

    E = pi * L * T / (4 N^2 n_obj^2), N being the working f-number
    1/(2 n' sin U') and n_obj the object-space index (L / n^2 is invariant,
    so an object immersed in index n_obj gives 1/n_obj^2).

    This is the standard camera equation: irradiance falls as 1/N^2, which
    is why a lens stopped down two stops needs four times the exposure.

    Args:
        object_radiance: Radiance of the object (W / (m^2 sr)).
        f_number: Working f-number.
        transmission: System transmission (0 to 1).
        n_image: Object-space refractive index (name kept for compatibility).
    """
    if f_number <= 0 or not math.isfinite(f_number):
        return 0.0
    n2 = max(1e-9, n_image * n_image)
    return math.pi * object_radiance * transmission / (4.0 * f_number * f_number * n2)


def relative_illumination_cos4(field_angle: float) -> float:
    """
    The cos^4 obliquity factor (thin lens in air, object at infinity).

    Identical to ``illumination.cos4_falloff``; provided here so the
    radiometric module is self-contained.
    """
    return math.cos(field_angle) ** 4


# =============================================================================
# Blackbody radiation
# =============================================================================

STEFAN_BOLTZMANN = 5.670374419e-8   # W / (m^2 K^4)
WIEN_B = 2.897771955e-3             # m K


def wien_peak_wavelength(temperature: float) -> float:
    """Wien displacement law: peak wavelength (m) of a blackbody."""
    if temperature <= 0:
        return 0.0
    return WIEN_B / temperature


def planck_spectral_radiance(temperature: float, wavelength: float) -> float:
    """
    Planck spectral radiance of a blackbody, per unit wavelength.

        L_lambda = 2 h c^2 / (lambda^5 (exp(h c / (lambda k T)) - 1))

    Args:
        temperature: Absolute temperature (K).
        wavelength: Wavelength (m).

    Returns:
        Spectral radiance in W / (m^2 sr m).
    """
    if wavelength <= 0 or temperature <= 0:
        return 0.0
    exp_arg = H_PLANCK * C_LIGHT / (wavelength * K_BOLTZMANN * temperature)
    if exp_arg > 700.0:
        return 0.0
    numerator = 2.0 * H_PLANCK * C_LIGHT * C_LIGHT
    denominator = (wavelength ** 5) * (math.exp(exp_arg) - 1.0)
    return numerator / denominator


def planck_spectral_exitance(temperature: float, wavelength: float) -> float:
    """Spectral exitance (W / (m^2 m)) = pi * spectral radiance."""
    return math.pi * planck_spectral_radiance(temperature, wavelength)


def stefan_boltzmann_exitance(temperature: float) -> float:
    """Total hemispherical exitance sigma T^4 (W / m^2)."""
    if temperature <= 0:
        return 0.0
    return STEFAN_BOLTZMANN * temperature ** 4


def _trapezoid(y, x) -> float:
    """Trapezoid rule (np.trapezoid in NumPy 2, np.trapz before)."""
    fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    return float(fn(y, x))


def band_integrated_radiance(temperature: float, wl_min: float, wl_max: float,
                             num_samples: int = 200) -> float:
    """Integrate Planck spectral radiance over a wavelength band."""
    if wl_max <= wl_min or num_samples < 2:
        return 0.0
    xs = np.linspace(wl_min, wl_max, num_samples)
    ys = [planck_spectral_radiance(temperature, float(x)) for x in xs]
    return _trapezoid(ys, xs)


def band_integrated_flux(temperature: float, wl_min: float, wl_max: float,
                         area: float, solid_angle: float,
                         num_samples: int = 200) -> float:
    """Radiant flux (W) collected from a blackbody over a band."""
    radiance = band_integrated_radiance(temperature, wl_min, wl_max, num_samples)
    return radiance * area * solid_angle


def blackbody_luminous_efficacy(temperature: float,
                                wl_min: float = 380e-9,
                                wl_max: float = 780e-9,
                                num_samples: int = 200) -> float:
    """
    Luminous efficacy of a blackbody radiator (lm / W).

    Integrates the Planck spectrum weighted by V(lambda) and divides by the
    total emitted power. Useful for sanity-checking lamp and emitter models
    (a 5800 K blackbody should land near 90-100 lm/W).
    """
    if temperature <= 0 or num_samples < 2:
        return 0.0
    xs = np.linspace(wl_min, wl_max, num_samples)
    visible = 0.0
    for x in xs:
        m = planck_spectral_exitance(temperature, float(x))
        visible += m * luminous_efficacy(float(x))
    total = stefan_boltzmann_exitance(temperature)
    if total <= 0 or len(xs) < 2:
        return 0.0
    step = (wl_max - wl_min) / (num_samples - 1)
    return visible * step / total


# =============================================================================
# BRDF models and reference database
# =============================================================================

@dataclass
class BRDFParameters:
    """
    Parameters of a bidirectional reflectance distribution function.

    Two families are supported:

        "lambertian"          f = rho / pi          (diffuse_fraction = rho)
        "abg" / "harvey-shack" f = A / (B + |beta|^g)

    The ABg (Harvey-Shack) form is the standard choice for stray-light
    analysis: it describes the smooth-angle-scattering tail of a polished
    or blasted surface.
    """
    model: str = "lambertian"
    diffuse_fraction: float = 0.1     # rho for lambertian
    A: float = 1.0e-2                 # ABg amplitude
    B: float = 1.0e-2                 # ABg shoulder
    g: float = 2.0                    # ABg slope exponent
    name: str = "custom"
    wavelength_range: tuple = (0.0, 0.0)
    source: str = ""


    target_tis: float = 0.0

    @classmethod
    def from_tis(cls, tis: float, B: float = 1.0e-3, g: float = 2.0,
                 **kwargs) -> "BRDFParameters":
        """
        Build an ABg entry from a total integrated scatter, not from A.

        TIS is the physically meaningful quantity: the fraction of incident
        power the surface scatters into the hemisphere, which must lie in
        [0, 1]. The ABg amplitude A is derived from it, which is how
        stray-light tools define these surfaces.

        Args:
            tis: Target total integrated scatter (0 to 1).
            B: ABg shoulder parameter.
            g: ABg slope exponent.
            **kwargs: Passed through to :class:`BRDFParameters`.
        """
        return cls(model="abg",
                   A=abg_amplitude_for_tis(tis, B, g),
                   B=B, g=g, target_tis=tis, **kwargs)

def brdf_lambertian(reflectance: float) -> float:
    """BRDF of a perfectly diffuse (Lambertian) surface: rho / pi."""
    return max(0.0, reflectance) / math.pi


def brdf_abg(parameters: BRDFParameters, beta: float) -> float:
    """
    Harvey-Shack ABg BRDF at a given scatter angle.

        f(beta) = A / (B + |beta|^g)

    Args:
        parameters: The BRDF parameters.
        beta: Distance from the specular direction in direction-cosine
            space, |sin(theta_s) - sin(theta_0)| (the ABg convention; equal
            to the angle in radians only for small angles near normal).

    Returns:
        BRDF value (1 / sr).
    """
    d = parameters.B + abs(beta) ** parameters.g
    if d <= 0:
        return 0.0
    return parameters.A / d


def brdf_value(parameters: BRDFParameters, beta: float = 0.0) -> float:
    """Evaluate a BRDF for the requested model."""
    if parameters.model.lower() in ("abg", "harvey-shack", "harveyshack"):
        return brdf_abg(parameters, beta)
    return brdf_lambertian(parameters.diffuse_fraction)


def _abg_hemisphere_integral(A, B, g, beta_max, num_samples):
    """
    Raw hemispherical integral of an ABg BRDF, without clamping.

    Integrates f(beta) cos(beta) dOmega over a cone of half-angle beta_max:
        integral = 2 pi A integral sin(b) cos(b) / (B + b^g) db
    """
    if num_samples < 2 or beta_max <= 0:
        return 0.0
    betas = np.linspace(0.0, beta_max, num_samples)
    values = []
    for b in betas:
        beta = float(b)
        denom = B + abs(beta) ** g
        if denom <= 0:
            values.append(0.0)
            continue
        values.append((A / denom) * math.cos(beta)
                      * 2.0 * math.pi * math.sin(beta))
    return _trapezoid(values, betas)


def abg_tis_per_unit_amplitude(B, g, beta_max=math.radians(85.0),
                               num_samples=400):
    """
    Hemispherical integral of the ABg shape evaluated at A = 1.

    This is the bridge between the shape parameters (B, g) and the
    amplitude A: TIS = A * I_shape.
    """
    return _abg_hemisphere_integral(1.0, B, g, beta_max, num_samples)


def abg_amplitude_for_tis(tis, B, g, beta_max=math.radians(85.0),
                          num_samples=400):
    """
    ABg amplitude A that produces the requested total integrated scatter.

    Solving TIS = A * I_shape for A gives A = TIS / I_shape, where
    I_shape comes from :func:`abg_tis_per_unit_amplitude`.

    Args:
        tis: Target total integrated scatter (clamped to 0 to 1).
        B: ABg shoulder parameter.
        g: ABg slope exponent.
        beta_max: Half-angle of the collection cone (radians).
        num_samples: Integration samples.
    """
    per_unit = abg_tis_per_unit_amplitude(B, g, beta_max, num_samples)
    if per_unit <= 0:
        return 0.0
    return max(0.0, min(1.0, tis)) / per_unit


def _is_abg(parameters):
    """True if the parameters describe a Harvey-Shack ABg surface."""
    model = (parameters.model or "").strip().lower()
    return model in ("abg", "harvey-shack", "harveyshack")


def total_integrated_scatter(parameters, beta_max=math.radians(85.0),
                             num_samples=400):
    """
    Fraction of incident power scattered into the hemisphere.

        TIS = integral f(beta) cos(beta) dOmega

    For a Lambertian surface this is exactly the reflectance. For the ABg
    form the integral is evaluated numerically.

    The result is clamped to [0, 1]. ABg is an empirical small-angle
    scattering fit, and evaluated with parameters from outside its fitted
    range its integral can exceed unity, which would mean the surface
    scatters more power than it receives. Database entries avoid this by
    construction, because they are defined from a target TIS.
    """
    if _is_abg(parameters):
        total = _abg_hemisphere_integral(parameters.A, parameters.B,
                                         parameters.g, beta_max, num_samples)
    else:
        total = parameters.diffuse_fraction
    return max(0.0, min(1.0, total))


# Reference BRDF entries for stray-light work.
#
# The ABg entries are anchored to a target total integrated scatter, which
# is the physically meaningful specification: the fraction of incident
# power the surface removes from the specular beam. A is derived from it
# through BRDFParameters.from_tis. The TIS values are order-of-magnitude
# assumptions for each kind of finish and B, g are arbitrary shape choices:
# these are illustrative models, not measurements. Substitute measured BRDF
# data for any real stray-light analysis.
#
#   TIS ~ 1e-5   superpolished, low-scatter laser optics
#   TIS ~ 1e-3   good commercial polish (0.1 percent)
#   TIS ~ 0.3    fine ground
#   TIS ~ 0.1-0.5 blasted, anodised, or machined metal
BRDF_DATABASE = {
    "superpolished_glass": BRDFParameters.from_tis(
        1.0e-5, B=1.0e-3, g=2.0, name="superpolished_glass",
        source="illustrative: assumed TIS 1e-5, superpolished low-scatter glass"),
    "polished_glass": BRDFParameters.from_tis(
        1.0e-3, B=1.0e-3, g=2.0, name="polished_glass",
        source="illustrative: assumed TIS 1e-3, commercial polish in the visible"),
    "fine_ground_glass": BRDFParameters.from_tis(
        3.0e-1, B=1.0e-2, g=2.0, name="fine_ground_glass",
        source="illustrative: assumed TIS 0.3, fine ground glass"),
    "black_anodized_aluminum": BRDFParameters.from_tis(
        1.0e-1, B=1.0e-2, g=2.0, name="black_anodized_aluminum",
        source="illustrative: assumed TIS 0.1, anodised aluminium in the visible"),
    "rough_aluminum": BRDFParameters.from_tis(
        5.0e-1, B=5.0e-2, g=2.0, name="rough_aluminum",
        source="illustrative: assumed TIS 0.5, roughened machined aluminium"),
    "matte_black_paint": BRDFParameters.from_tis(
        2.0e-1, B=2.0e-2, g=2.0, name="matte_black_paint",
        source="illustrative: assumed TIS 0.2, flat black paint"),
    "polished_gold": BRDFParameters.from_tis(
        1.0e-3, B=1.0e-3, g=2.0, name="polished_gold",
        source="illustrative: assumed TIS 1e-3, evaporated gold, infrared band"),
    "spectralon": BRDFParameters(
        model="lambertian", diffuse_fraction=0.99,
        name="spectralon",
        source="PTFE reflectance standard, TIS = reflectance"),
    "barium_sulfate": BRDFParameters(
        model="lambertian", diffuse_fraction=0.95,
        name="barium_sulfate",
        source="BaSO4 reflectance coating, TIS = reflectance"),
    "black_felt": BRDFParameters(
        model="lambertian", diffuse_fraction=0.02,
        name="black_felt",
        source="black felt light trap, TIS = reflectance"),
}

def get_brdf(name: str) -> Optional[BRDFParameters]:
    """Look up a reference BRDF by name (case-insensitive)."""
    key = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    return BRDF_DATABASE.get(key)


def list_brdf_names() -> list:
    """Return the sorted names of the reference BRDF entries."""
    return sorted(BRDF_DATABASE.keys())
