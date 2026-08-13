# Optics Reference

This document describes the optical conventions, formulas, and assumptions used in the AI Optical Design Engineer.

## Sign Convention

The project uses the **optics sign convention** (as used in optical design software like Zemax):

- Light travels from left to right along the z-axis.
- Ray heights above the optical axis (y-axis) are positive.
- Ray angles measured counterclockwise from the optical axis are positive.
- Object distance (s): **NEGATIVE** if the object is to the **left** of the lens.
- Object distance (s): **POSITIVE** if the object is to the **right** of the lens.
- Image distance (s'): **NEGATIVE** if the image is to the **left** of the lens.
- Image distance (s'): **POSITIVE** if the image is to the **right** of the lens.
- Focal length (f): positive for **converging** lenses, negative for **diverging** lenses.

## Unit System

- All internal calculations use **SI base units**: meters (m) for length, radians (rad) for angles.
- The UI displays values in millimeters (mm) and degrees for convenience.
- The `optics/units.py` module is the single source of truth for unit conversions.
- Supported length units: nm, μm (um), mm, cm, m, km.
- Supported angle units: rad, deg, mrad.

## Fundamental Equations

### Thin Lens Equation

```
1/f = 1/s' - 1/s
```

Where:
- f = focal length
- s = object distance (NEGATIVE if object is to the left)
- s' = image distance (POSITIVE if image is to the right)

Solved for image distance:
```
s' = f * s / (s + f)
```

Example: Object at 2f to the left (s = -2f), image at 2f to the right (s' = +2f):
```
1/f = 1/(2f) - 1/(-2f) = 1/(2f) + 1/(2f) = 1/f  ✓
```

### Magnification

```
m = s' / s
```

- Negative magnification means the image is **inverted**.
- |m| > 1 means the image is **larger** than the object.
- |m| < 1 means the image is **smaller** than the object.

Example: Object at 2f to the left, image at 2f to the right:
```
m = (2f) / (-2f) = -1  ✓ (inverted, same size)
```

### F-number

```
F/# = f / D
```

Where D is the aperture diameter. F/2 means the focal length is twice the aperture diameter.

### Numerical Aperture

```
NA = n * sin(θ)
```

Where:
- n = refractive index of the medium (1.0 for air)
- θ = half-angle of the cone of light entering/exiting the lens

### Effective Focal Length (Two-Lens System)

```
1/f_eff = 1/f1 + 1/f2 - d/(f1*f2)
```

Where d is the distance between the two lenses.

## Ray Transfer Matrix (ABCD Matrix) Method

Rays are represented as vectors [y, θ] where y is height and θ is angle.

### Free-space propagation over distance d:

```
[y']   [1  d] [y]
[θ'] = [0  1] [θ]
```

### Thin lens with focal length f:

```
[y']   [1   0] [y]
[θ'] = [-1/f 1] [θ]
```

The overall system matrix is the product of individual matrices, applied left-to-right as the ray travels.

### Effective focal length from system matrix:

If M = [[A, B], [C, D]], then:
```
f_eff = -1 / C
```

## Paraxial Approximation

All ray tracing uses the **paraxial (small-angle) approximation**:
- sin(θ) ≈ θ
- tan(θ) ≈ θ
- cos(θ) ≈ 1

This is valid for small angles (typically < 5°). Rays that pass through different aperture heights should all converge to the same paraxial image point, giving an RMS spot radius of ~0.

## Spherical Surface Refraction (Phase 2)

### Surface power:

```
Φ = (n2 - n1) / R
```

Where R is the radius of curvature (positive if center of curvature is to the right of the surface).

### Image distance:

```
n1/s + n2/s' = (n2 - n1) / R
```

### Lensmaker's equation (thick lens):

```
1/f = (n - 1) * [1/R1 - 1/R2 + (n-1)*t / (n * R1 * R2)]
```

Where:
- R1, R2 = radii of curvature of the two surfaces
- t = lens thickness
- n = refractive index

## Materials

Refractive indices are provided at the Fraunhofer e-line (587.6 nm). Sellmeier coefficients are available for wavelength-dependent calculations in Phase 2.

## Ray Types

- **Chief ray**: Passes through the center of the aperture (y = 0 at the first lens). Defines the optical axis path.
- **Marginal ray**: Passes through the edge of the aperture. Defines the aperture stop.
- **Fill ray**: Evenly distributed between chief and marginal rays. Fills the aperture.

## Key Assumptions

1. **Monochromatic light**: Single wavelength (default 550 nm) for the MVP.
2. **Paraxial rays**: Small-angle approximation throughout.
3. **Thin lenses**: No lens thickness; all refraction at a single plane.
4. **No diffraction**: Spot diagrams show geometric ray intersections only.
5. **Sequential tracing**: Rays follow a single path through the system (no scattering, no diffraction, no interference).
