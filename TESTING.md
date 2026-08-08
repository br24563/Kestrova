# Testing Guide

## Overview

Testing is critical for an optical design application. Physical correctness must be verified against known cases. All tests use physically meaningful values, not just "does it run without errors."

## Backend Tests (pytest)

### Running Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

Run a specific test file:
```bash
pytest tests/test_lenses.py -v
```

Run a specific test:
```bash
pytest tests/test_lenses.py::TestImageDistance::test_object_at_2f_produces_image_at_2f -v
```

Run with coverage:
```bash
pip install pytest-cov
pytest tests/ --cov=optics --cov-report=term-missing
```

### Test Organization

Tests are organized by module:

| Test File | Tests |
|-----------|-------|
| `test_units.py` | Unit conversions (nm, mm, cm, degrees, etc.) |
| `test_lenses.py` | Thin lens equations, magnification, two-lens systems, ABCD matrices |
| `test_rays.py` | Ray propagation, refraction, ray generation, ray tracing, spot diagrams |
| `test_systems.py` | System creation, component management, validation |
| `test_analysis.py` | EFL, magnification, F-number, NA, full system analysis |

### Writing New Tests

1. **Use known physical cases**: Test against hand-calculated or textbook values.
2. **Use `pytest.approx`**: Floating-point comparisons need tolerance.
3. **Test both positive and negative cases**: E.g., converging and diverging lenses.
4. **Test edge cases**: Object at infinity, object at focal point, etc.

Example test:
```python
def test_object_at_2f_produces_image_at_2f(self):
    """Object at 2f should produce image at 2f (symmetric case)."""
    f = 0.050  # 50 mm
    s = 0.100  # 100 mm = 2f
    s_prime = image_distance(f, s)
    assert s_prime == pytest.approx(0.100, rel=1e-10)
```

### Key Physical Test Cases

| Case | Expected Result |
|------|----------------|
| Object at 2f | Image at 2f, magnification = -1 |
| Object at 3f | Image at 1.5f, magnification = -0.5 |
| Object at f | Image at infinity (error) |
| Object inside f | Virtual image (s' < 0), magnification positive |
| Parallel rays | Converge at focal point |
| Two lenses touching | EFL = f1*f2 / (f1+f2) |

## Frontend Tests (Vitest)

Frontend tests use Vitest. Currently the frontend has no test files, but the framework is set up.

```bash
cd frontend
npm run test
```

To add tests:
```bash
npm run test -- --watch
```

## Test-First Development

For any new mathematical functionality:

1. Write the test first with a known physical case.
2. Run the test — it should fail.
3. Implement the function.
4. Run the test — it should pass.
5. Run the full test suite to check for regressions.

## Continuous Verification

Before committing, always run:
```bash
cd backend && pytest tests/ -v
```

This ensures all 119 tests pass before any code change.
