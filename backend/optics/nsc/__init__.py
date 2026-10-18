"""Non-sequential ray tracing module."""

from .system import NSCSystem, Source, Detector, Object3D, Vector3, Ray, HitPoint
from .tracer import NSCTracer
from .scatter import ScatterModel, LambertianScatter, GaussianScatter, ABgScatter
from .asphere import AsphericSurface, OddAsphericSurface, QTypeSurface
from .enhancements import (
    VolumeProperties,
    beer_lambert_transmittance,
    apply_volumetric_absorption,
    FluorescenceModel,
    compute_fluorescence_intensity,
    generate_fluorescent_rays,
    SpectralSource,
    create_blackbody_spectrum,
    create_gaussian_spectrum,
    wavelength_to_rgb,
    compute_rgb_from_spectrum,
    export_rays_to_file,
    import_rays_from_file,
)

__all__ = [
    "NSCSystem",
    "Source",
    "Detector",
    "Object3D",
    "Vector3",
    "Ray",
    "HitPoint",
    "NSCTracer",
    "ScatterModel",
    "LambertianScatter",
    "GaussianScatter",
    "ABgScatter",
    "AsphericSurface",
    "OddAsphericSurface",
    "QTypeSurface",
    "VolumeProperties",
    "beer_lambert_transmittance",
    "apply_volumetric_absorption",
    "FluorescenceModel",
    "compute_fluorescence_intensity",
    "generate_fluorescent_rays",
    "SpectralSource",
    "create_blackbody_spectrum",
    "create_gaussian_spectrum",
    "wavelength_to_rgb",
    "compute_rgb_from_spectrum",
    "export_rays_to_file",
    "import_rays_from_file",
]
