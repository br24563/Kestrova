"""
Reference optical system data from published textbooks.

Sources:
- Born & Wolf, "Principles of Optics", 7th Edition
- Smith, "Modern Optical Engineering", 4th Edition
- Hecht, "Optics", 5th Edition
- SCHOTT optical glass data sheets (N-BK7, N-SF11)
- I. H. Malitson, J. Opt. Soc. Am. 55, 1205 (1965) (fused silica)

All values are in SI units (meters, radians) unless noted. Material indices
are the published values, not values computed by this code.
"""

import math

# =============================================================================
# Paraxial Reference Cases
# =============================================================================

# Thin lens equation: 1/f = 1/s' - 1/s
# Sign convention: s < 0 (object left), s' > 0 (image right)

PARAXIAL_CASES = [
    # (f, s, expected_s_prime, description)
    {
        "f": 0.100,  # 100mm
        "s": -0.200,  # 2f
        "expected_s_prime": 0.200,  # 2f
        "expected_magnification": -1.0,
        "description": "Object at 2f, image at 2f (symmetric)",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.3",
    },
    {
        "f": 0.100,
        "s": -0.300,  # 3f
        "expected_s_prime": 0.150,  # 1.5f
        "expected_magnification": -0.5,
        "description": "Object at 3f, image at 1.5f",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.3",
    },
    {
        "f": 0.100,
        "s": -0.150,  # 1.5f
        "expected_s_prime": 0.300,  # 3f
        "expected_magnification": -2.0,
        "description": "Object at 1.5f, image at 3f (magnifying)",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.3",
    },
    {
        "f": 0.100,
        "s": -0.500,  # 5f
        "expected_s_prime": 0.125,  # 1.25f
        "expected_magnification": -0.25,
        "description": "Object at 5f, image at 1.25f (reducing)",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.3",
    },
    {
        "f": 0.100,
        "s": -0.050,  # f/2 (inside focal point)
        "expected_s_prime": -0.100,  # virtual image
        "expected_magnification": 2.0,
        "description": "Object inside f, virtual upright image",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.3",
    },
]

# Two-lens system: 1/f_eff = 1/f1 + 1/f2 - d/(f1*f2)
TWO_LENS_CASES = [
    # (f1, f2, d, expected_efl, description)
    {
        "f1": 0.100,
        "f2": 0.100,
        "d": 0.050,
        "expected_efl": 0.066667,  # 66.67mm
        "description": "Two 100mm lenses, 50mm separation",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.5",
    },
    {
        "f1": 0.100,
        "f2": 0.100,
        "d": 0.0,
        "expected_efl": 0.050,  # 50mm (touching)
        "description": "Two 100mm lenses touching",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.5",
    },
    {
        "f1": 0.100,
        "f2": -0.100,
        "d": 0.050,
        "expected_efl": 0.200,  # 200mm (Galilean)
        "description": "100mm positive + -100mm negative, 50mm sep",
        "source": "Hecht, Optics, 5th Ed., Section 5.2.5",
    },
]

# =============================================================================
# Snell's Law Reference Cases
# =============================================================================

SNELL_CASES = [
    # (n1, n2, theta1, expected_theta2, description)
    {
        "n1": 1.0,
        "n2": 1.5,
        "theta1": 0.0,
        "expected_theta2": 0.0,
        "description": "Normal incidence, no refraction",
        "source": "Hecht, Optics, 5th Ed., Section 4.4",
    },
    {
        "n1": 1.0,
        "n2": 1.5,
        "theta1": math.radians(30),
        "expected_theta2": math.asin(1.0 * math.sin(math.radians(30)) / 1.5),
        "description": "Air to glass, 30 degree incidence",
        "source": "Hecht, Optics, 5th Ed., Section 4.4",
    },
    {
        "n1": 1.5,
        "n2": 1.0,
        "theta1": math.radians(30),
        "expected_theta2": math.asin(1.5 * math.sin(math.radians(30)) / 1.0),
        "description": "Glass to air, 30 degree incidence",
        "source": "Hecht, Optics, 5th Ed., Section 4.4",
    },
]

# Critical angle for glass (n=1.5) to air: arcsin(1/1.5) = 41.81 degrees
CRITICAL_ANGLE_CASES = [
    {
        "n1": 1.5,
        "n2": 1.0,
        "expected_critical_angle": math.asin(1.0 / 1.5),
        "description": "Critical angle, glass to air",
        "source": "Hecht, Optics, 5th Ed., Section 4.5",
    },
    {
        "n1": 1.5168,  # N-BK7 at d-line
        "n2": 1.0,
        "expected_critical_angle": math.asin(1.0 / 1.5168),
        "description": "Critical angle, N-BK7 to air",
        "source": "Schott Catalog",
    },
]

# =============================================================================
# Diffraction Reference Cases
# =============================================================================

# Airy disk radius: r_airy = 1.22 * lambda * f_number
AIRY_DISK_CASES = [
    # (wavelength, f_number, expected_airy_radius, description)
    {
        "wavelength": 550e-9,
        "f_number": 2.0,
        "expected_airy_radius": 1.22 * 550e-9 * 2.0,
        "description": "f/2 at 550nm",
        "source": "Born & Wolf, Principles of Optics, 7th Ed., Section 8.5",
    },
    {
        "wavelength": 550e-9,
        "f_number": 5.6,
        "expected_airy_radius": 1.22 * 550e-9 * 5.6,
        "description": "f/5.6 at 550nm",
        "source": "Born & Wolf, Principles of Optics, 7th Ed., Section 8.5",
    },
    {
        "wavelength": 632.8e-9,  # HeNe laser
        "f_number": 10.0,
        "expected_airy_radius": 1.22 * 632.8e-9 * 10.0,
        "description": "f/10 at 632.8nm (HeNe)",
        "source": "Born & Wolf, Principles of Optics, 7th Ed., Section 8.5",
    },
]

# MTF cutoff frequency: f_cutoff = 1 / (lambda * f_number)
MTF_CUTOFF_CASES = [
    # (wavelength, f_number, expected_cutoff, description)
    {
        "wavelength": 550e-9,
        "f_number": 2.0,
        "expected_cutoff": 1.0 / (550e-9 * 2.0),
        "description": "f/2 at 550nm",
        "source": "Born & Wolf, Principles of Optics, 7th Ed., Section 8.6",
    },
    {
        "wavelength": 550e-9,
        "f_number": 5.6,
        "expected_cutoff": 1.0 / (550e-9 * 5.6),
        "description": "f/5.6 at 550nm",
        "source": "Born & Wolf, Principles of Optics, 7th Ed., Section 8.6",
    },
]

# =============================================================================
# Material Reference Data
# =============================================================================

# Published line indices (F 486.13 nm, d 587.56 nm, C 656.27 nm).
SCHOTT_INDICES = [
    {"material": "N-BK7", "wavelength_nm": 486.13, "expected_n": 1.52238, "tolerance": 1e-4},
    {"material": "N-BK7", "wavelength_nm": 587.56, "expected_n": 1.51680, "tolerance": 1e-4},
    {"material": "N-BK7", "wavelength_nm": 656.27, "expected_n": 1.51432, "tolerance": 1e-4},
    {"material": "N-SF11", "wavelength_nm": 486.13, "expected_n": 1.80645, "tolerance": 1e-4},
    {"material": "N-SF11", "wavelength_nm": 587.56, "expected_n": 1.78472, "tolerance": 1e-4},
    {"material": "N-SF11", "wavelength_nm": 656.27, "expected_n": 1.77599, "tolerance": 1e-4},
    # Malitson (1965)
    {"material": "FusedSilica", "wavelength_nm": 486.13, "expected_n": 1.46313, "tolerance": 1e-4},
    {"material": "FusedSilica", "wavelength_nm": 587.56, "expected_n": 1.45846, "tolerance": 1e-4},
    {"material": "FusedSilica", "wavelength_nm": 656.27, "expected_n": 1.45637, "tolerance": 1e-4},
]

# Published Abbe numbers vd = (nd - 1) / (nF - nC).
ABBE_NUMBERS = [
    {"material": "N-BK7", "expected_vd": 64.17, "tolerance": 0.05},
    {"material": "N-SF11", "expected_vd": 25.68, "tolerance": 0.05},
    {"material": "FusedSilica", "expected_vd": 67.82, "tolerance": 0.05},
]
