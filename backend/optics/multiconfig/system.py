"""
Multi-configuration optical system.

A multi-config system can have different states (configurations)
that share some parameters but differ in others.
"""

from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from ..models import (
    OpticalSystem,
    ThinLens,
    ThickLens,
    Object,
    ImagePlane,
    AnalysisSettings,
)


class ConfigType(str, Enum):
    """Types of configurations."""

    ZOOM = "zoom"
    FOCUS = "focus"
    TEMPERATURE = "temperature"
    WAVELENGTH = "wavelength"
    FIELD = "field"


@dataclass
class Configuration:
    """A single configuration state."""

    config_id: int
    config_type: ConfigType
    name: str = ""

    # Configuration parameters
    zoom_position: float = 0.0  # Zoom position (0-1)
    focus_distance: float = float("inf")  # Object distance
    temperature: float = 20.0  # Celsius
    pressure: float = 101.325  # kPa

    # Wavelength weights
    wavelength_weights: dict[float, float] = field(default_factory=dict)

    # Field weights
    field_weights: dict[float, float] = field(default_factory=dict)

    # Variable parameters (differ between configs)
    variables: dict[str, float] = field(default_factory=dict)

    def apply_to_system(self, system: OpticalSystem) -> OpticalSystem:
        """
        The system in this configuration.

        - ``variables``: parameter name -> value, names as in
          :mod:`optics.tolerance` (e.g. "L2.position"); unknown names raise.
        - ``wavelength_weights``: sets the system's wavelength list (the
          weights stay on the configuration). The analysis/reference
          wavelength is not changed, because thin-lens focal lengths are
          defined at it.
        - ``focus_distance`` (m): places the object that far in front of the
          first surface.
        - ``temperature`` for TEMPERATURE configurations: applies glass
          expansion and thin-lens index change (see optics.thermal); systems
          with thick lenses need ThermalAnalyzer, which also changes their
          glass indices, and raise here.
        """
        from ..tolerance import set_parameter

        config_system = system
        for var_name, value in self.variables.items():
            config_system = set_parameter(config_system, var_name, value)
        if self.wavelength_weights:
            config_system = config_system.model_copy(
                update={"wavelengths": [float(w) for w in self.wavelength_weights]}
            )
        if self.focus_distance != float("inf"):
            first = min(c.position for c in config_system.components)
            obj = config_system.object.model_copy(
                update={"position": first - self.focus_distance}
            )
            config_system = config_system.model_copy(update={"object": obj})
        if self.config_type == ConfigType.TEMPERATURE and self.temperature != 20.0:
            if any(isinstance(c, ThickLens) for c in config_system.components):
                raise ValueError(
                    "Thick-lens index changes with temperature need "
                    "optics.thermal.ThermalAnalyzer"
                )
            from ..thermal.analysis import thermal_system

            config_system, _ = thermal_system(config_system, self.temperature)
        return config_system


@dataclass
class ZoomConfig(Configuration):
    """Zoom lens configuration."""

    config_type: ConfigType = ConfigType.ZOOM
    focal_length: Optional[float] = None  # nominal label (m); not applied
    zoom_ratio: float = 1.0  # nominal label; not applied


@dataclass
class FocusConfig(Configuration):
    """Focus configuration."""

    config_type: ConfigType = ConfigType.FOCUS
    object_distance: float = float("inf")  # m from the first surface
    focus_group_shift: float = 0.0  # label only; move groups via ``variables``

    def __post_init__(self):
        if self.object_distance != float("inf"):
            self.focus_distance = self.object_distance


@dataclass
class ThermalConfig(Configuration):
    """Thermal configuration."""

    config_type: ConfigType = ConfigType.TEMPERATURE
    temperature: float = 20.0  # Celsius
    housing_material: str = ""  # label only; mount expansion is not applied here


@dataclass
class WavelengthConfig(Configuration):
    """Wavelength configuration."""

    config_type: ConfigType = ConfigType.WAVELENGTH
    wavelengths: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)


@dataclass
class MultiConfigSystem:
    """Multi-configuration optical system."""

    base_system: OpticalSystem
    configurations: list[Configuration] = field(default_factory=list)

    # Common parameters (shared across configs)
    common_params: list[str] = field(default_factory=list)

    # Variable parameters (differ between configs)
    variable_params: dict[str, list[float]] = field(default_factory=dict)

    def add_config(self, config: Configuration) -> int:
        """Add a configuration."""
        config.config_id = len(self.configurations)
        self.configurations.append(config)
        return config.config_id

    def get_config(self, config_id: int) -> Optional[Configuration]:
        """Get configuration by ID."""
        for config in self.configurations:
            if config.config_id == config_id:
                return config
        return None

    def get_system(self, config_id: int) -> OpticalSystem:
        """Get optical system for a configuration."""
        config = self.get_config(config_id)
        if config is None:
            return self.base_system
        return config.apply_to_system(self.base_system)

    def analyze_all(self) -> list[dict]:
        """Analyze all configurations."""
        from ..analysis import analyze_system

        results = []
        for config in self.configurations:
            system = config.apply_to_system(self.base_system)
            analysis = analyze_system(system)
            results.append(
                {
                    "config_id": config.config_id,
                    "config_name": config.name,
                    "analysis": analysis,
                }
            )
        return results

    def get_variable_range(self, param: str) -> tuple[float, float]:
        """Get range of a variable parameter across configs."""
        values = [
            config.variables.get(param, 0)
            for config in self.configurations
            if param in config.variables
        ]
        if not values:
            return (0, 0)
        return (min(values), max(values))
