"""Standard optical components.

Provides:
- Prisms (right angle, Porro, Dove, etc.)
- Fold mirrors
- Beam splitters
- Windows
- Filters
"""

from .prism import (
    Prism,
    RightAnglePrism,
    PorroPrism,
    DovePrism,
    RoofPrism,
    PentaPrism,
    WedgePrism,
    create_prism,
)
from .mirror import FoldMirror, DichroicMirror
from .splitter import BeamSplitCube, BeamSplitPlate

__all__ = [
    "Prism",
    "RightAnglePrism",
    "PorroPrism",
    "DovePrism",
    "RoofPrism",
    "PentaPrism",
    "WedgePrism",
    "create_prism",
    "FoldMirror",
    "DichroicMirror",
    "BeamSplitCube",
    "BeamSplitPlate",
]
