"""
AI Optical Design Engineer - Core Optics Engine

A local-first, open-source optical design and ray-tracing engine.

This package contains the core optical calculations, independent of any
user interface. It can be used directly from Python or through the
FastAPI backend.

Modules:
    raytrace  - Sequential engine all analyses are built on: surface
                sequence, paraxial first-order properties, exact 3D real-ray
                tracing with ray aiming, OPD and Seidel sums
    pupil     - Pupil wavefront grids, FFT PSF/MTF and Strehl ratio
    zernike   - Zernike polynomials (Noll, Fringe, annular) and fitting
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
    diffraction - PSF, MTF, OTF, Airy disk, encircled energy
    base      - Dependency-free base model for optical components
    high_order - Ray fans, OPD maps, field curves, through-focus MTF
    advanced_surfaces - Aspheres (even/odd/Q-type), Zernike, DOE,
                toric, and coordinate-break surfaces
    glass_optimization - Glass substitution, glass expert, merit builder
    wavefront - Wavefront maps, Zernike decomposition, interferograms
    mechanical - Lens barrels/housings and ISO 10110 drawings
    performance - Parallel tracing, ray caching, BSP acceleration
    standards - Zemax-style tolerance operands, PartBuilder, Lens Data
                Editor, Merit Function Editor, inverse tolerancing,
                and multiple unit systems
    illumination - Vignetting, relative illumination (cos^4), MTF field
                and focus maps
    radiometry - Radiometric and photometric quantities (flux, radiance,
                illuminance, luminous efficacy), Planck blackbody, and
                BRDF models with a reference surface database
    ghost     - Double-reflection ghost analysis with real bidirectional
                ray paths, ghost focus and ghost spot size
    imaging   - Image simulation: test targets, PSF, illumination,
                distortion, and a full sensor model (noise, full well, ADC)
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
    parameter_sweep, optimize_system, multi_objective_optimize,
    minimize_rms_spot, target_magnification, target_efl,
    CONSTRAINT_PENALTY,
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
from .diffraction import (
    airy_disk_radius, psf, encircled_energy,
    mtf, otf, diffraction_limited_check, diffraction_analysis,
)
from .batch import batch_analyze_systems, batch_sweep_and_analyze
from .tolerance import tolerance_analysis
from .report import (
    compare_systems, system_spot_svg, engineering_report_markdown,
)
from .high_order import (
    ray_fan, opd_map, field_curves, through_focus_mtf,
    zernike_from_rays, high_order_analysis,
)
from .advanced_surfaces import (
    AsphericSurface, OddAsphericSurface, QAsphericSurface,
    ZernikeSurface, DiffractiveOpticalElement, ToricSurface,
    CoordinateBreak,
)
from .glass_optimization import (
    GlassRegion, GlassCandidate, GlassSubstitutionResult,
    GlassExpertResult, MeritFunction, Operand,
    get_glasses_in_region, find_nearest_glasses,
    substitute_glass, evaluate_glass_substitution,
    find_best_glass_substitution, glass_expert_optimize,
    compute_partial_derivatives, build_standard_merit_function,
)
from .wavefront import (
    WavefrontMap, ZernikeDecomposition, InterferogramData,
    SeidelCoefficients, WavefrontAnalysisResult,
    compute_wavefront_map, zernike_decompose,
    simulate_interferogram, compute_seidel_from_wavefront,
    full_wavefront_analysis,
)
from .mechanical import (
    LensMount, BarrelSection, ISO10110Symbol, ISO10110Drawing,
    generate_lens_mount, generate_barrel_from_system, generate_barrel_mesh,
    create_iso10110_drawing, iso10110_to_svg,
)
from .performance import (
    trace_rays_parallel, trace_rays_batched, RayTraceCache,
    AABB, BSPNode, SpatialAccelerator,
    BenchmarkResult, benchmark_ray_tracing, benchmark_all,
)
from .standards import (
    OperandType, ToleranceOperand,
    PartDefinition, build_part_from_spec,
    SurfaceRow, LensDataEditor,
    MeritOperandRow, MeritFunctionEditor, MERIT_OPERAND_MAP,
    operand_to_parameter, select_compensators,
    inverse_sensitivity_tolerance, build_tolerance_operands,
    operands_to_tolerance_specs,
    UnitSystem, UNIT_SYSTEMS, convert_unit_system, EXTRA_LENGTH_UNITS,
)

from .illumination import (
    VignettingResult, cos4_falloff, chief_ray_image_angle,
    vignetting_at_field, vignetting_analysis,
    relative_illumination, mtf_field_map, mtf_focus_map,
    illumination_summary,
)
from .radiometry import (
    photopic_luminosity, luminous_efficacy, radiant_to_luminous,
    luminous_to_radiant, photon_energy, photon_flux,
    solid_angle_cone, solid_angle_from_f_number,
    f_number_from_numerical_aperture, numerical_aperture_from_f_number,
    etendue, etendue_from_f_number, irradiance_from_flux,
    illuminance_from_flux, radiance_from_irradiance,
    image_irradiance_from_object, relative_illumination_cos4,
    wien_peak_wavelength, planck_spectral_radiance,
    planck_spectral_exitance, stefan_boltzmann_exitance,
    band_integrated_radiance, band_integrated_flux,
    blackbody_luminous_efficacy,
    BRDFParameters, brdf_lambertian, brdf_abg, brdf_value,
    total_integrated_scatter, BRDF_DATABASE, get_brdf, list_brdf_names,
)
from .ghost import (
    GhostSurface, GhostResult,
    fresnel_reflectance, normal_incidence_reflectance,
    build_surface_chain, trace_ghost_path, chief_ray, pupil_fan,
    primary_image_height, analyze_ghosts, ghost_analysis,
)
from .imaging import (
    SensorConfig, SimulationResult, TEST_TARGETS,
    effective_f_number, working_f_number, magnification,
    object_pixel_pitch, field_of_view,
    airy_psf, psf_for_system, rms_spot_radius,
    test_target, sensor_response, simulate_image,
    distortion_curve, relative_illumination_profile,
    relative_illumination_map,
    mtf_from_bar_target, image_quality_metrics, image_statistics,
    bars_band_rows, encode_png_gray, save_png, ascii_preview,
)
