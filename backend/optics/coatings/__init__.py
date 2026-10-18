"""Thin film coating module.

Features:
- Single and multi-layer coatings
- Anti-reflection coatings
- High-reflectivity mirrors
- Beam splitters
- Edge filters
- Bandpass filters
- Coating design and optimization
"""
from .layer import Layer, MaterialLayer
from .coating import Coating, design_ar_coating, design_hr_coating, design_beam_splitter
from .transfer_matrix import transfer_matrix, reflection_transmission, electric_field


__all__ = [
    'Layer', 'MaterialLayer',
    'Coating', 'design_ar_coating', 'design_hr_coating', 'design_beam_splitter',
    'transfer_matrix', 'reflection_transmission', 'electric_field',
]
