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

## Lens Data (surface prescription)

`optics/lens_data.py` holds the Code V / Zemax style prescription: an
ordered list of surfaces, each with a thickness to the next surface, so a
change of one thickness moves everything after it. Thicknesses after a
mirror are negative. Parameters can be variables (for the optimizer),
solved (thickness from a marginal or chief ray height; radius from a ray
slope or an F-number) or picked up from another surface
(`scale * source + offset`). Solves use the engine's own paraxial trace;
they and pickups are re-applied in surface order until nothing changes.
Unset semi-diameters are the largest real-ray height at the surface over
the pupil edge at the axial and full fields for all wavelengths. A lens
converts to the component model below (and back) without changing the
optics.

## How the Engine Traces Rays

All analyses are built on one sequential engine (`backend/optics/raytrace.py`).

### Paraxial (first-order) trace

First-order properties come from a y-nu paraxial trace with signed indices
(a mirror reverses the direction of travel and the sign of the index):
EFL, BFL, FFL, principal planes, the paraxial image, the entrance and exit
pupils and the Lagrange invariant. The aperture stop is the `ApertureStop`
component, or otherwise the surface that limits the axial beam.

### Exact (real) ray trace

Spot diagrams, wavefronts, MTF, PSF, vignetting and relative illumination
use **exact 3D real rays**: vector Snell's law at every refracting surface,
exact intersection with spherical, conic and aspheric surfaces, and rays
aimed iteratively so that pupil coordinates map onto the real stop.
No small-angle approximation is made in these analyses.

### Ideal (thin) lenses

A `ThinLens` is an *ideal paraxial lens*, like Zemax's paraxial surface:
it maps ray direction tangents as t' = t - (x, y)/f, which images every
pair of conjugate planes without aberration. It therefore shows first-order
behaviour and chromatic effects only (its focal length scales with
wavelength as (n_ref - 1)/(n(lambda) - 1) of its glass, with f defined at
the analysis reference wavelength). Use `ThickLens`, surfaces and mirrors
to see real aberrations.

## Single Surface Refraction

### Surface power

```
Φ = (n2 - n1) / R
```

R is positive if the centre of curvature is to the right of the surface.

### Imaging by one surface (same sign convention as above, s < 0 to the left)

```
n2/s' - n1/s = (n2 - n1) / R
```

### Lensmaker's equation (thick lens in air)

```
1/f = (n - 1) * [1/R1 - 1/R2 + (n-1)*t / (n * R1 * R2)]
BFL = f * (1 - (n - 1) * t / (n * R1))
```

## Fields and Wavelengths

A system may carry a Code V style field table: points in x and y as object
heights, field angles (direction tangents tan x, tan y) or paraxial image
heights, each with a weight and vignetting factors VUX, VLX, VUY, VLY that
limit its pupil to -(1 - VL) .. (1 - VU). Wavelengths may be weighted.
Without a table the fields are 0, 0.7 and 1 of the object height along y.
Field analyses and the optimizer's ray-error merit use the table and the
weights; off-axis tangential MTF is taken along each field's image
direction.

RMS spot sizes integrate over the pupil area by Gaussian quadrature
(G. W. Forbes, JOSA A 5, 1943, 1988): ring radii at Gauss-Legendre nodes
in r^2, each ray weighted by its share of the pupil area.

## Aberrations and Image Quality

- **Seidel (third-order) sums** S1 to S5, CL and CT follow Welford,
  *Aberrations of Optical Systems*. Wavefront coefficients are
  W040 = S1/8, W131 = S2/2, W222 = S3/2, W220 = (S3 + S4)/4, W311 = S5/2.
  Real-ray measures are reported alongside for comparison.
- **OPD** is W = OPL(chief) - OPL(ray) on a reference sphere centred on
  the chief ray's image point and passing through the exit pupil (a plane
  wave for an image at infinity).
- **PSF and MTF** are FFTs of the pupil function built from the real-ray
  OPD. The Strehl ratio is |sum P|^2 / (sum A)^2 over the pupil.
- **Diffraction limited** means Strehl >= 0.8 (Maréchal criterion,
  about lambda/14 RMS wavefront error).
- **Relative illumination** is the projected solid angle of the real ray
  bundle at each field point relative to the axis (it includes cos^4
  obliquity, pupil aberrations and vignetting).

## Materials

Glass data comes from the vendors' own catalog files: SCHOTT, OHARA, HOYA
and CDGM (820 glasses; see `backend/tools/build_glass_catalog.py`).
Crystals, IR materials, polymers and water use published dispersion
formulas, each with its citation in `backend/optics/materials.py`.
Every index comes from the dispersion formula and is refused outside the
wavelength range the source states. Properties a source does not give are
left empty rather than estimated.

Reference wavelengths: d line 587.56 nm (helium), e line 546.07 nm
(mercury), F line 486.13 nm, C line 656.27 nm.

## Ray Types

- **Chief ray**: from the edge of the field through the centre of the aperture stop.
- **Marginal ray**: from the axial object point through the edge of the aperture stop.
- **Fill rays**: a grid of rays across the pupil.

## Key Assumptions and Limits

1. Sequential tracing: each ray meets the surfaces in a fixed order.
   Non-sequential tracing lives in `optics/nsc` and is separate.
2. Ideal thin lenses are aberration-free by construction (see above).
3. Polychromatic analyses sample the wavelengths you list.
4. Coatings, polarization and scatter are modelled in their own modules
   and are not yet folded into the sequential image-quality analyses.
