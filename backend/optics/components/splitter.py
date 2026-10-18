"""
Beam splitter components.

Provides cube and plate beam splitters.
"""

from typing import Optional
from dataclasses import dataclass
from ..nsc.system import Object3D, Vector3


@dataclass
class BeamSplitCube(Object3D):
    """Cube beam splitter."""
    
    def __init__(self, position=None, size=25.4, ratio=0.5, coating="dielectric"):
        super().__init__(
            name="BeamSplitCube",
            position=position or Vector3(),
            object_type="splitter",
        )
        self.size = size
        self.ratio = ratio  # Reflection ratio
        self.coating = coating
        self.reflectivity = ratio
        self.transmission = 1 - ratio


@dataclass
class BeamSplitPlate(Object3D):
    """Plate beam splitter."""
    
    def __init__(self, position=None, normal=None, size=25.4, ratio=0.5, 
                 coating="dielectric", compensate=False):
        super().__init__(
            name="BeamSplitPlate",
            position=position or Vector3(),
            object_type="splitter",
        )
        self.normal = normal or Vector3(0, 1, 1).normalized()
        self.size = size
        self.ratio = ratio
        self.coating = coating
        self.compensate = compensate  # Compensate for lateral displacement
        self.reflectivity = ratio
        self.transmission = 1 - ratio
