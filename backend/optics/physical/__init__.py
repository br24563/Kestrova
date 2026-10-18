"""Physical optics module.

Features:
- Gaussian beam propagation
- Diffraction propagation (Fresnel, Fraunhofer)
- Fiber coupling
- Coherence modeling
"""
from .gaussian import (
    GaussianBeam, BeamParameter, ABCDMatrix,
    propagate_beam, free_space_propagation, lens_transform, calculate_M2
)
from .diffraction import (
    fresnel_diffraction, fraunhofer_diffraction, angular_spectrum_propagation,
    calculate_diffraction_limit, point_spread_function, optical_transfer_function,
    modulation_transfer_function
)
from .fiber import (
    Fiber, SingleModeFiber, MultiModeFiber,
    coupling_efficiency, alignment_sensitivity, optimal_coupling_lens
)
from .coherence import (
    TemporalCoherence, SpatialCoherence,
    interference_pattern, fringe_visibility, michelson_interferometer,
    fabry_perot_interferometer
)
from .laser_source import (
    LaserDiode, LEDSource, SLSource,
    compute_transfer_function, compute_otf,
    partially_coherent_image, compute_mtf, compute_psf,
)

__all__ = [
    'GaussianBeam',
    'BeamParameter',
    'ABCDMatrix',
    'propagate_beam',
    'free_space_propagation',
    'lens_transform',
    'calculate_M2',
    'fresnel_diffraction',
    'fraunhofer_diffraction',
    'angular_spectrum_propagation',
    'calculate_diffraction_limit',
    'point_spread_function',
    'optical_transfer_function',
    'modulation_transfer_function',
    'Fiber',
    'SingleModeFiber',
    'MultiModeFiber',
    'coupling_efficiency',
    'alignment_sensitivity',
    'optimal_coupling_lens',
    'TemporalCoherence',
    'SpatialCoherence',
    'interference_pattern',
    'fringe_visibility',
    'michelson_interferometer',
    'fabry_perot_interferometer',
    'LaserDiode', 'LEDSource', 'SLSource',
    'compute_transfer_function', 'compute_otf',
    'partially_coherent_image', 'compute_mtf', 'compute_psf',
]
