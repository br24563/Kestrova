"""
AI Optical Design Engineer - Core Optics Engine

A local-first, open-source optical design and ray-tracing engine.

This package contains the core optical calculations, independent of any
user interface. It can be used directly from Python or through the
FastAPI backend.

Modules:
    units     - Centralized unit handling and conversions
    models    - Data models for optical systems and components
    lenses    - Thin lens calculations
    surfaces  - Spherical refractive surface calculations
    rays      - Ray tracing engine
    systems   - Optical system assembly and management
    materials - Refractive index data
    analysis  - Optical analysis (focal length, NA, F-number, etc.)
    optimization - Parameter sweeps and numerical optimization
    aberration - Chromatic aberration analysis
    real_rays  - Exact (Snell's law) ray tracing for aberration analysis
    seidel     - Seidel (third-order) monochromatic aberration analysis
"""

__version__ = "0.1.0"

# Re-export key functions and classes for convenience
from .units import (
    Quantity, to_meters, from_meters, to_radians, from_radians,
    convert, is_length_unit, is_angle_unit,
)
from .models import (
    OpticalSystem, ThinLens, SphericalSurface, ThickLens, ApertureStop, Mirror,
    Object, ImagePlane, AnalysisSettings,
    Ray, RayPath, RayTraceResult, AnalysisResult,
    OpticalComponent,
)
from .lenses import (
    image_distance, object_distance, focal_length,
    magnification, magnification_from_f,
    two_lens_effective_focal_length, two_lens_back_focal_length,
    two_lens_front_focal_length, two_lens_system_image,
    RayVector, propagation_matrix, thin_lens_matrix,
    apply_matrix, system_matrix,
    f_number, numerical_aperture, half_angle_from_na,
)
from .rays import (
    propagate, reflect_at_mirror, refract_at_thin_lens,
    generate_rays, trace_ray, trace_system,
    calculate_paraxial_image_position, calculate_paraxial_image_height,
    calculate_spot_diagram,
)
from .systems import (
    create_default_system, get_lenses, get_first_lens, get_last_lens,
    get_component_by_id, add_component, remove_component,
    update_component, move_component, sort_components, validate_system,
)
from .analysis import (
    build_system_matrix, effective_focal_length,
    back_focal_length, front_focal_length,
    system_magnification, object_distance as system_object_distance,
    image_distance as system_image_distance, working_distance,
    system_f_number, system_numerical_aperture, analyze_system,
)
from .surfaces import (
    spherical_surface_power, spherical_surface_image_distance,
    spherical_surface_refract, lensmaker_focal_length,
)
from .materials import refractive_index, refractive_index_sellmeier
from .optimization import (
    parameter_sweep, optimize_system,
    minimize_rms_spot, target_magnification, target_efl,
)
from .aberration import (
    F_LINE, D_LINE, C_LINE,
    image_position_at_wavelength, image_height_at_wavelength,
    longitudinal_chromatic_aberration, lateral_chromatic_aberration,
    chromatic_aberration_analysis,
)
from .real_rays import (
    trace_real_ray, real_intercept_at_plane, real_axis_crossing,
    real_ray_crossing,
)
from .seidel import (
    spherical_aberration, coma, astigmatism_and_field_curvature,
    distortion, seidel_analysis,
)
