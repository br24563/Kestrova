# Roadmap: bringing Kestrova to Code V level

This document compares Kestrova with Code V, lists the gaps and sets out
the work that closes them.

**Summary.** Kestrova covers the core loop of a conventional
imaging-lens design: prescription, exact rays, constrained optimization,
wavefront tolerancing, diffraction MTF, and file and CAD output. Its
methods deliberately follow Code V. It is not yet at Code V level in
breadth, in speed on aspheric systems, or in accuracy proven across many
designs. Parity for rotationally symmetric imaging lenses is a realistic
target. Full parity is a multi-year effort.

**Basis.** The comparison comes from reading Kestrova's code and
documentation (November 2026, after version 0.4.0) and a few timings. No
results were compared with Code V itself, and the Code V feature list is
from general knowledge of the program: check option names against its
documentation before relying on them.

## Where Kestrova stands

| Area | Kestrova today | Code V | Gap |
|---|---|---|---|
| Lens data | Solves, pickups, zoom table, field table with vignetting, 11 surface types | Dozens of surface types, several decenter types, non-sequential surface ranges | Medium |
| Ray trace | Exact 3D with ray aiming; compiled kernel for conics, aspheres, XY polynomials and diffractive surfaces | Compiled throughout | Medium |
| Optimization | Damped least squares with exact constraints; 19 property kinds | Same method; hundreds of constraints, any ray datum, user-defined, MTF | Large |
| Global search | Sobol multi-start | Global Synthesis | Large |
| Tolerancing | Fast wavefront-differential method, 13 types, RMS wavefront only, one configuration | Also MTF, distortion and other metrics; irregularity, wedge, asphere, homogeneity; all zooms | Large |
| Image analysis | FFT and Hopkins MTF, PSF, encircled energy, through-focus, field plots, Seidel | Adds line spread, footprint, distortion grid, full-field maps, fifth order | Medium |
| Physical optics | Polarization trace, coatings, paraxial Gaussian beam, scalar PSF | Vector PSF, diffraction beam propagation, partial coherence, fiber coupling | Large |
| Stray light, thermal | Exact double-bounce ghosts, temperature and pressure | Adds narcissus, illumination | Small to medium |
| Manufacturing | ISO 10110 drawings, STEP/IGES, report | Test-plate fitting, cost, weight, cam, interferogram data | Medium |
| Interchange | `.seq` reader handles about 25 commands; configuration 1 only | n/a | Medium |
| Automation | Python API; console starts a fresh process per run | Macro language, command line, COM | Small |
| Validation | 5 reference lenses plus closed forms | Decades of industrial use | Largest |

## Structural issues

These are not missing features. They slow every later phase, so Phase 1
deals with them.

- **Two generations of code coexist:**
  - `tolerance.py` and `tolerancing.py`;
  - `optimization.py`, `advanced_optimization.py` and `lens_optimize.py`;
  - `ghost.py` and `ghost_trace.py`;
  - `/api/analyze/*` alongside `/api/lens/*`.
- **Some modules are not connected to the prescription.** `grin/`,
  `nsc/`, `physical/fiber.py`, `physical/diffraction.py` and
  `wavefront.py` never reference `LensData`, so their features cannot be
  used on a real lens.
- **Some surface types run on the slow path.** The compiled kernel
  (`_fasttrace.py`) handles spheres, conics, even and odd aspheres, XY
  polynomials and diffractive surfaces. A lens with a Q asphere, Zernike
  surface, toroid or ideal lens uses the NumPy trace throughout.
- **There is no licence file.** This blocks outside adoption and
  contribution.

## Plan

### Phase 1: foundation

- Extend the compiled kernel to every surface type.
  - Done: spheres, conics, even and odd aspheres, XY polynomials and
    diffractive surfaces, in any frames (coordinate breaks included).
  - Left: Q aspheres, Zernike surfaces, toroids and ideal lenses. The
    first three take their gradients numerically in the NumPy trace, so
    they need analytic gradients first.
- Retire the legacy modules and make `LensData` the only system model.
- Add a licence.
- Build a regression corpus of 50 to 100 patent lenses with stored
  first-order, exact-ray and MTF results.

*Done when* a 20-surface aspheric lens optimizes at kernel speed and the
corpus runs in CI.

### Phase 2: core design parity

- **Operands and constraints:**
  - any ray datum at any surface (height, incidence angle, path length);
  - MTF at a frequency and field;
  - user-defined operands written in Python.
- **Tolerance types:** irregularity, wedge, conic and asphere terms,
  index homogeneity.
- **Tolerance metrics:** MTF and distortion besides RMS wavefront, and
  all configurations in one run.
- **Analyses:** footprint, line spread function, distortion grid,
  Zernike fit across the field, fifth-order aberrations.
- **Lens files:** read and write the zoom table, and widen the `.seq`
  and `.zmx` coverage.

*Done when* the corpus lenses round-trip through `.seq` with no
warnings.

### Phase 3: global optimization

- Replace multi-start with an escape-function or saddle-point search.
- Add an advisor for where to place aspheres.
- Benchmark against published global-search problems, such as the
  monochromatic quartet.

*Done when* the search finds the published solutions of those problems.

### Phase 4: surfaces and systems

- Anamorphic and biconic surfaces, reflective and linear gratings,
  Fresnel surfaces and user-defined surfaces.
- GRIN and birefringent materials in the prescription.
- Decenter-and-return and bend.
- Non-sequential surface ranges inside a sequential lens.

*Done when* each type has a closed-form or published check, as
ARCHITECTURE.md requires for a new surface type.

### Phase 5: physical optics

- Vector PSF with apodization from coatings and polarization.
- Huygens PSF.
- Diffraction beam propagation through the real lens.
- Fiber coupling from the traced wavefront.
- Partial coherence, narcissus and illumination.

*Done when* each analysis matches a closed form or a published result.

### Phase 6: manufacturing

- Test-plate fitting.
- Weight and cost.
- Cam curves for zoom lenses.
- Measured interferogram maps on surfaces.
- As-built Monte Carlo output files.

*Done when* a toleranced design can go to a shop from Kestrova's output
alone.

### Throughout: validation

Cross-check against Code V output wherever someone with a licence can
supply it. That is the only direct proof of parity. Until then the
corpus, closed forms and other programs (ray-optics) stand in.

## Priorities

Phases 1 and 2 matter most: they make "works the way Code V does" hold
for everyday lens design. Phases 4 to 6 can be reordered by what users
need.
