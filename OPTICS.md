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

Surface types (each on a base conic, `radius` 0 = flat, unless noted):

| Type | Sag beyond the conic | Parameters |
|---|---|---|
| standard | none | |
| even asphere | A4 r^4 .. A20 r^20 | `asphere_4` .. `asphere_20` |
| odd asphere | the even terms plus A3 r^3 .. A19 r^19 | `asphere_3` .. `asphere_19` |
| Q asphere | Forbes Qbfs (best-fit sphere) or Qcon terms over `norm_radius` | `q_0` .. `q_12` |
| toroid | the y-z conic swept about an axis parallel to y at `radius_x` (0 = cylinder) | `radius_x` |
| Zernike | standard (Noll) Zernike terms over `norm_radius` | `z_1` .. `z_37` |
| XY polynomial | C_ij (x/R)^i (y/R)^j, 1 <= i + j <= 10, R = `norm_radius` | `x<i>y<j>` |
| diffractive | phase c_1 r^2 + c_2 r^4 + .. (radians) in `diffraction_order` | `phase_2` .. `phase_20` |

plus paraxial (ideal lens), coordinate break and engine component. All the
named terms can be variables or pickups. Mirrors can take any of these
shapes except diffractive (a reflection grating is not supported yet). A diffractive surface adds
(m lambda / 2 pi) grad(phi) to the tangential component of n d at its
(curved) base surface, so its paraxial power -c_1 m lambda / pi adds to the
base surface's refraction. Paraxial data of a surface without rotational
symmetry (toroid, Zernike, XY polynomial) use its y-z section; Seidel sums
list such surfaces as unsupported.

Every surface can also carry a central circular obscuration and a
rectangular or elliptical clear aperture (half-widths in x and y) besides
its circular semi-diameter; rays outside are vignetted in every analysis.
The aperture stop stays circular. A chief ray stopped by an obscuration
still serves as the wavefront reference.

### Reference lenses

`optics/reference_lenses.py` holds published designs with the results
their sources report, and `tests/test_reference_lenses.py` checks the
engine against them. The app offers them as samples.

| Lens | Source | Checked |
|---|---|---|
| Geiser triplet, f/4, 50 mm | Sasian, OPTI 517, via ray-optics | EFL, BFL, FFL, pupils, paraxial ray heights, Seidel S-I..S-V on every surface, wavefront coefficients: all to the printed digits |
| Cell-phone lens, f/3.5 (US 7,535,658) | ray-optics | First-order data; three exact rays (marginal, skew, off-axis chief) through 8 odd/even aspheres: every intersection, sag and direction cosine to the printed digits |
| Double Gauss, f/1.7 (US 2,784,643) | Smith, *Modern Lens Design*, via COMSOL | EFL 100.2 mm within 0.05 %; axial minimum-RMS focus 0.186 mm vs. COMSOL's 0.180 mm |
| Field-flattened Petzval, f/2.4 | Kidger, *Fundamental Optical Design*, via COMSOL | EFL within 0.8 % (glasses substituted) |
| Hubble Space Telescope | COMSOL model; STScI | EFL 57.6 m and f/24 within 0.01 %; spherical aberration and coma cancel between the mirrors |

The surface types and apertures are checked against closed-form results
in `tests/test_surface_types.py`: the Forbes Q polynomials against Forbes'
recurrence (Opt. Express 18, 19700 (2010)), Zernike terms against their XY
polynomial expansions, a tilted XY plane against Snell's law at a wedge,
the diffractive surface against the grating equation and its Abbe number
(-3.45), and the MTF of an obscured perfect lens against O'Neill's
annular-pupil MTF and of a square pupil (1 - v/a) to 1e-3.

Hopkins direct integration handles blocked parts of the pupil
(obscurations, shaped apertures, vignetting by any surface) by splitting
its quadrature at their edges: each Gauss line across the pupil overlap is
divided where rays start or stop passing (found by probing and bisection),
and the lines are grouped into panels wherever the number of unblocked
pieces changes, so no Gauss rule straddles an edge. All frequencies are
integrated together.

The ray-optics comparisons are against an independent program tracing
the same prescription, so they test the engine to the last printed digit.
The designers' focal lengths are for their original glasses, which the
tabulated copies replace with catalogue equivalents, so they hold to about
1 %.

### Diffraction MTF

The MTF is the modulus of the optical transfer function, the normalised
autocorrelation of the pupil function P = A exp(i 2 pi W / lambda) over the
real-ray wavefront W. Kestrova computes it two independent ways
(`optics/pupil.py`, `optics/mtf_analysis.py`):

- **FFT**: P sampled on a square grid in normalised stop coordinates,
  zero-padded, autocorrelated by FFT and sliced along the tangential and
  sagittal directions. Fast; its accuracy is limited by the grid.
- **Hopkins direct integration** (Hopkins 1957): for each frequency, the
  overlap integral (1/A) of P(p + s/2) P*(p - s/2) over the lens-shaped
  overlap of the pupil and its shifted copy, by Gauss-Legendre quadrature,
  with W traced at the quadrature points themselves. No grid and no
  aliasing.

A shift of one pupil diameter corresponds to the cutoff 2 NA' / lambda.
For an aberration-free circular pupil both match
(2/pi)(acos x - x sqrt(1 - x^2)), x = nu / nu_c: Hopkins to about 1e-4 with
48 nodes per axis, the FFT to about 3e-3 on a 64-sample grid. With a
quarter wave of defocus both agree with the analytic defocus OTF to 2e-3.
Polychromatic MTF is the weighted sum of each wavelength's complex OTF.

**PSF and energy.** The PSF is the FFT of the pupil function; for several
wavelengths each is shifted by its chief-ray position (lateral colour),
normalised to unit energy and weighted. Encircled and ensquared energy are
summed on each wavelength's native FFT grid about the polychromatic
centroid; for an aberration-free pupil they match 1 − J0² − J1² to about
1.5 % (the square pupil grid approximating the circle). The FFT window
spans about ±26 Airy radii for a 64-sample pupil: a blur wider than that
(strongly aberrated lenses) is flagged rather than silently wrapped around.

**Field plots.** Distortion is the real chief-ray height relative to the
paraxial height; F-θ distortion (object at infinity) is relative to f·θ, so
an ideal lens, which maps f·tanθ, shows (tanθ − θ)/θ. Lateral colour is
each wavelength's real chief-ray height minus the reference wavelength's,
in the reference paraxial image plane.

**Through focus.** The best focus at a given frequency lies between the
paraxial focus and beyond the minimum-RMS-wavefront focus; for an
uncorrected lens these are far apart and the MTF can have several local
peaks. The default scan therefore searches that whole region coarsely and
then scans +-4 lambda N'^2 about the highest point, following the peak if it
lands on an edge. For a corrected lens this reduces to +-4 lambda N'^2
about the image plane.

### Tolerancing

`optics/tolerancing.py` tolerances a prescription the way Code V's TOR
does.

**Tolerance types** (Code V names):

- **DLF (radius in fringes):** changes the exact conic sag at the test
  diameter by Nλ/2.
- **DLN, DLV (index and Abbe number):** use a perturbed glass,
  `PERTURB:<glass>:<dn>:<dVd>`, with n'(λ) = nd + dn + k(n(λ) − nd). This
  shifts nd and Vd exactly and keeps the catalog's partial dispersions.
- **Decenters and tilts:** a coordinate break before the surfaces and its
  exact inverse after them (Rx(−tx) then Ry(−ty), with the origin returned
  to the axis). Element tilts pivot on the first vertex.

**Performance** is the RMS wavefront error with piston and tilt removed,
over the field table and wavelengths, on a Gaussian pupil quadrature.

**The fast method** traces each tolerance at ±limit and each compensator by
central differences. This gives a model of the wavefront residual vector
that is quadratic in each tolerance (cross terms neglected) and linear in
the compensators. Compensators are fitted by bounded least squares. The
predicted distribution comes from Monte Carlo on the model.
`tolerancing.monte_carlo` is the exact reference. On a cemented achromat
with five times the default tolerances, the two agree within the sampling
noise of the exact run (mean 0.1118 vs 0.1117 waves, 84 % level 0.140 vs
0.135).

### Optimization

`optics/lens_optimize.py` minimises the transverse ray errors (fields 0,
0.7 and 1, all wavelengths, Gaussian pupil) by damped least squares with
the lens's constraints held exactly, as Code V does: each cycle solves the
KKT system of the damped normal equations and the linearised active
constraints (an active-set iteration, or a small QP solve where that
cycles), then takes a second-order correction step back onto curved
constraints. Steps are accepted on an exact-penalty merit; a final Newton
restoration meets the constraints to round-off. Radii vary as curvatures
(power, and so focal length, is nearly linear in them), and radius bounds
may not span a flat surface.

Constraints are targets or limits on EFL, BFL, working F-number,
magnification, total track, the centre thickness after a surface, or the
edge thickness after a surface, measured at the smaller of the two
semi-diameters with the exact sag.

A model glass, `MODEL:<nd>:<vd>`, has the dispersion
n = A + B/λ² + C/λ⁴ (λ in µm) fitted exactly to nd, to nF − nC = (nd − 1)/Vd
and to a partial dispersion on Schott's normal line,
P_g,F = 0.6438 − 0.001682 Vd (SCHOTT TIE-29), valid 0.38 to 1.0 µm. Its
nd and Vd can be variables; the optimizer keeps them inside the convex hull
of the vendor glasses' (nd, Vd) points. `snap_glasses` then replaces each
model glass by the nearest catalog glass, with 0.01 in nd counting as 1 in
Vd and SCHOTT inquiry glasses skipped; re-optimize after snapping.

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

### Speed

Sequences made only of spheres and conics (refracting or reflecting),
stops and dummies, in any frames, are traced by a compiled kernel
(`optics/_fasttrace.py`, Numba) that performs the same operations as the
NumPy trace ray by ray; small batches run serially and large ones (4096+
rays) in parallel. Other surfaces use the NumPy trace. Without Numba, or
with `OPTICS_NO_NUMBA=1`, everything uses NumPy and gives the same results.

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
