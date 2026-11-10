# Testing Guide

## The rule

Every test compares the engine with something it did not compute:

- a closed form;
- a published design and its published results;
- vendor catalog data;
- another program's output;
- an exact Monte Carlo.

The engine is never checked against its own formulas. When a test and
the code disagree, find out which one is right before changing either.

## Size

| Suite | Tests | Where |
|-------|-------|-------|
| Backend (pytest) | about 1,640 | `backend/tests/`, one file per area |
| Frontend (Vitest) | about 170 | beside the components (`*.test.tsx`), plus `src/__tests__` and `src/*.test.ts` |

CI fails if the backend's coverage of `optics/` drops below 80%. It is
about 86% now. `pytest -q` prints the current count.

## Running

```bash
cd backend
pytest tests/ -q                                       # everything (several minutes)
pytest tests/ --cov=optics --cov-fail-under=80        # with the CI gate
pytest tests/test_reference_lenses.py -v              # one area
pytest tests/test_tolerancing.py -k inverse           # matching tests

cd ../frontend
npm test -- --run
```

The tolerancing, global-search, Monte Carlo and script-console tests
start worker processes or trace millions of rays. They make up most of
the backend run time.

## What is validated, and against what

| Area | Reference | Tests |
|------|-----------|-------|
| Glass indices | SCHOTT data sheets; every vendor glass against its catalog nd; Malitson, Li and Tatian for crystals and IR materials | `test_materials`, `test_glass_catalog` |
| First order and real rays | Published lenses: first-order data, paraxial rays, Seidel sums and exact rays through even and odd aspheres against ray-optics' printed output; designers' focal lengths; COMSOL's best focus; Hubble's focal length and aplanatism | `test_reference_lenses` |
| Lenses and surfaces | Lensmaker equation, thick-lens EFL and BFL, mirror sag h²/4R, paraboloid without spherical aberration, Snell's law and TIR | `test_scientific_validation`, `test_surfaces`, `test_rays` |
| Surface types | Closed-form sags (conic, Q-type with Gauss-Legendre normalisation, Zernike, XY, toroid), DOE grating equation | `test_surface_types` |
| Aberrations | Third-order aberrations against real rays at small aperture, Petzval sum from curvatures | `test_seidel`, `test_high_order` |
| Diffraction | Airy radius, 83.8% encircled energy at the first dark ring, MTF 0.391 at half cutoff, the obscured-pupil MTF | `test_diffraction`, `test_mtf_analysis`, `test_image_quality` |
| Illumination | Exact off-axis irradiance of a disk | `test_scientific_validation`, `test_illumination` |
| Optimization | Constraints met exactly; a two-group zoom reaching the focal lengths of the closed form; global search returning both independently bracketed optima of an achromat's bending | `test_lens_optimize`, `test_merit`, `test_configurations`, `test_global_lens` |
| Tolerancing | The predicted distribution against exact Monte Carlo builds | `test_tolerancing` |
| Polarization and coatings | Fresnel equations, the quarter-wave AR layer, ideal mirror phases | `test_polarization_trace`, `test_coatings` |
| Environment and ghosts | The Edlén / Birch-Downs air index, a singlet's thermal focal shift, a plate's ghost focus 2t/n before the image | `test_environment_ghost_beam` |
| Gaussian beams | S. A. Self's thin-lens waist formulas | `test_environment_ghost_beam` |
| Files | Code V and Zemax round trips keep the first-order values and Seidel sums; files in inches against hand conversion | `test_lensfile` |
| CAD | Element volumes against the closed form (cylinder plus spherical segments); STEP shells closed (every edge used once in each sense); IGES fixed-format records; when OpenCascade is installed, the files read back as valid solids with the right volumes | `test_cad_layout` |
| Drawings and reports | Edge thickness from the sphere sag, ISO 10110 CX/CC sense, tolerance codes | `test_scripting_reports` |
| Script console | Isolation, time limit, and refusal of non-loopback clients, Host headers and Origins | `test_scripting_reports` |
| Compiled trace | The Numba kernel against the NumPy trace, ray by ray | `test_fasttrace` |
| Desktop engine | User-data folder, the served interface, the free port and `KESTROVA_PORT` line, exiting when its input closes, the kernel cache folder | `test_desktop_backend`, `test_cad_layout` |

Robustness tests (`test_edge_cases`, `test_numerical_stability`,
`test_bug_finding`) cover:

- objects at infinity or at the focal point;
- extreme focal lengths;
- tiny perturbations;
- random inputs.

## Writing a test

- **Compare with an independent value**, and say where it comes from in
  the module docstring or the test name.
- **Use realistic values**, in SI units: focal lengths of 10–500 mm,
  visible wavelengths, catalog glasses.
- **Set tolerances from the reference.** A program's printed output
  supports 4–6 significant figures; a closed form supports much more.
  `pytest.approx(expected, rel=...)` states it.
- **Build lenses with `LensData`**, or start from a sample:
  `kestrova.sample("geiser-triplet")`.

```python
import math
import pytest
import kestrova as ks
from optics.lens_data import LensData, LensSurface
from optics.materials import refractive_index


def test_singlet_focal_length_matches_the_lensmaker_equation():
    r1, r2, t = 0.05, -0.08, 0.004
    lens = ks.Lens(
        LensData(
            surfaces=[
                LensSurface(radius=r1, thickness=t, material="N-BK7",
                            semi_diameter=0.01, is_stop=True),
                LensSurface(radius=r2, thickness=0.09, semi_diameter=0.01),
            ],
            field_angle=math.radians(2),
            wavelengths=[587.5618e-9],
        )
    )
    # first-order values are at the reference wavelength
    # (analysis_settings.wavelength, 550 nm unless set)
    n = refractive_index("N-BK7", lens.data.analysis_settings.wavelength)
    power = (n - 1) * (1 / r1 - 1 / r2 + (n - 1) * t / (n * r1 * r2))
    assert lens.efl == pytest.approx(1 / power, rel=1e-9)
```

## Continuous integration

The tests run on every push and pull request to `master`. See
[CI_CD.md](./CI_CD.md) for the platforms, the lint checks and the desktop
build's smoke test.

## References

- M. Born and E. Wolf, *Principles of Optics*, 7th ed.
- W. J. Smith, *Modern Optical Engineering*, 4th ed.
- W. T. Welford, *Aberrations of Optical Systems*
- S. A. Self, "Focusing of spherical Gaussian beams", *Appl. Opt.* 22,
  658 (1983)
- The SCHOTT, OHARA, HOYA and CDGM glass catalogs
