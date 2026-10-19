# Testing Guide

## Overview

This project uses a comprehensive testing strategy to ensure scientific correctness, reliability, and performance.

## Test Statistics

The backend suite has about 1,100 tests (`pytest tests/ -q` prints the
current count). The frontend tests in `frontend/src/__tests__` need
`npm install` (they use `@testing-library/react`).

## Running Tests

### Backend Tests

```bash
cd backend
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=optics --cov-report=term-missing

# Run specific test file
pytest tests/test_edge_cases.py -v

# Run specific test
pytest tests/test_edge_cases.py::TestObjectAtInfinity -v

# Run performance tests
pytest tests/test_performance.py -v

# Run with the CI coverage threshold (a ratchet at the current 68%;
# the target is 80%, see Coverage Targets)
pytest tests/ --cov=optics --cov-fail-under=68
```

### Frontend Tests

```bash
cd frontend
npm test -- --run
```

## Test Organization

```
tests/
├── test_units.py                  # Unit conversion tests
├── test_lenses.py                 # Thin lens equation tests
├── test_rays.py                   # Ray tracing tests
├── test_systems.py                # System assembly tests
├── test_analysis.py               # Optical analysis tests
├── test_materials.py              # Material property tests
├── test_optimization.py           # Optimization tests
├── test_aberration.py             # Chromatic aberration tests
├── test_diffraction.py            # Diffraction analysis tests
├── test_seidel.py                 # Seidel aberration tests
├── test_ai_commands.py            # AI command tests
├── test_persistence.py            # Database tests
├── test_project_tools.py          # Project tool tests
├── test_validation.py             # Input validation tests
├── test_validation_suite.py       # Physics validation tests
├── test_edge_cases.py             # Edge case tests
├── test_numerical_stability.py    # Numerical stability tests
├── test_scientific_validation.py  # Scientific validation tests
├── test_performance.py            # Performance benchmarks
├── test_bug_finding.py            # Bug finding tests
└── test_workflows.py              # Integration workflow tests
```

## Test Categories

### Unit Tests

Test individual functions and components:
- Unit conversions (nm, μm, mm, cm, m)
- Thin lens equations
- Ray tracing
- Material properties

### Edge Case Tests

Test boundary conditions:
- Object at infinity
- Object at focal point
- Zero/negative aperture
- Extreme focal lengths
- Very fast/slow optics

### Numerical Stability Tests

Test floating point precision:
- Small perturbations (1e-12)
- Large dynamic range (1e-9 to 1e3)
- Matrix operation stability
- Cancellation error avoidance

### Scientific Validation Tests

Compare the engine with results computed independently, never with the
engine's own formulas:
- Refractive indices against the SCHOTT data sheets and published
  literature (Malitson, Li, Tatian), and every vendor glass against its own
  catalog nd
- Thick-lens EFL and BFL against the lensmaker equation
- Exact defocus wavefront geometry; aberration-free ideal lenses
- Airy radius, 83.8 % encircled energy at the first dark ring, MTF 0.391
  at half cutoff, and the FFT MTF of a perfect lens
- Relative illumination against the exact off-axis disk irradiance
- Spherical mirror h^2/(4R), paraboloid without spherical aberration,
  Petzval sum from surface curvatures, third-order aberrations against
  real rays at small aperture
- Snell's law and total internal reflection in the exact tracer

### Performance Tests

Benchmark execution speed:
- Ray tracing: < 50ms for 11 rays
- Analysis: < 100ms
- Optimization: < 5s for 2 variables
- Tolerance: < 2s for 50 trials

### Bug Finding Tests

Systematic bug detection:
- Fuzzing with random inputs
- Property-based testing
- Differential testing
- Regression tests

### Integration Tests

End-to-end workflows:
- Design → Optimize → Analyze
- Import → Export → Import
- Multi-wavelength analysis
- Tolerance → Sensitivity → Re-optimize

## Writing New Tests

### Test Structure

```python
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.models import OpticalSystem, ThinLens

class TestMyFeature:
    """Test suite for MyFeature."""
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        # Arrange
        system = OpticalSystem(
            components=[ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025)],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        # Act
        result = analyze_system(system)
        
        # Assert
        assert result.effective_focal_length > 0
```

### Test Naming

- Test files: `test_<feature>.py`
- Test classes: `Test<FeatureName>`
- Test functions: `test_<description>`

### Test Data

Use realistic optical values:
- Focal lengths: 10mm to 500mm
- Wavelengths: 400nm to 700nm (visible)
- Aperture diameters: 1mm to 50mm
- Refractive indices: 1.4 to 1.8

### Assertions

Use pytest.approx for floating point:
```python
assert value == pytest.approx(expected, rel=1e-6)
```

Check for finite values:
```python
import math
assert math.isfinite(result)
```

## Coverage

### Running Coverage

```bash
pytest tests/ --cov=optics --cov-report=html
```

### Coverage Targets

| Module | Target |
|--------|--------|
| optics/units.py | 95% |
| optics/lenses.py | 95% |
| optics/rays.py | 90% |
| optics/analysis.py | 90% |
| optics/optimization.py | 85% |
| optics/tolerance.py | 80% |
| **Overall** | **80%** |

## Continuous Integration

Tests run automatically on:
- Push to main/master
- Pull requests to main/master
- Version tags (v*)

See `.github/workflows/test.yml` for details.

## Troubleshooting

### Tests Fail After Code Changes

1. Run the specific failing test:
   ```bash
   pytest tests/test_file.py::TestClass::test_name -v
   ```

2. Check for:
   - Changed function signatures
   - Modified data structures
   - Updated validation rules

### Coverage Drops Below Threshold

1. Identify uncovered code:
   ```bash
   pytest tests/ --cov=optics --cov-report=term-missing
   ```

2. Add tests for uncovered lines

### Performance Tests Fail

1. Check system load
2. Run tests individually
3. Adjust thresholds if needed

## References

- Born & Wolf, "Principles of Optics", 7th Edition
- Smith, "Modern Optical Engineering", 4th Edition
- Hecht, "Optics", 5th Edition
- Schott Glass Catalog, 2024
