# Kestrova

[![Version](https://img.shields.io/badge/version-0.4.0-orange)](./CHANGELOG.md)
[![Tests](https://github.com/br24563/Kestrova/actions/workflows/test.yml/badge.svg)](https://github.com/br24563/Kestrova/actions/workflows/test.yml)
[![Lint](https://github.com/br24563/Kestrova/actions/workflows/lint.yml/badge.svg)](https://github.com/br24563/Kestrova/actions/workflows/lint.yml)

Kestrova is a free, local-first optical design program. It is built on a
Python optics engine, a FastAPI backend, a React interface and an
Electron desktop app. It works the way Code V and Zemax do:

- a surface-by-surface lens data editor;
- exact real-ray analysis;
- constrained optimization and global search;
- fast tolerancing;
- physical optics;
- interchange with Code V and Zemax files and with CAD.

Every result is checked against an independent reference (published
designs, closed forms or other programs), never against the engine
itself.

## Quick start

- **Desktop app:** Windows and macOS (Apple Silicon and Intel)
  installers with the engine bundled are built by CI, and each version
  tag publishes them on the Releases page. See
  [desktop-app/README.md](./desktop-app/README.md), which also covers
  signing.
- **From source:** run `./launch.sh` (Linux/macOS), `launch.bat` or
  `.\launch.ps1` (Windows). The launcher sets up Python and Node and
  opens the app in your browser. [QUICKSTART.md](./QUICKSTART.md) has
  the manual steps.

Then open **Samples** in the Lens Data Editor and pick a published lens
to start from.

## Features

### Lens design

- **Lens data editor:** Code V / Zemax style, with undo and redo.
  - Thicknesses, radii, conics and surface data.
  - Solves (paraxial image, ray heights and angles, F-number), pickups
    and variable flags.
  - Field tables (object height, angle or image height, with weights and
    vignetting) and wavelength weights.
- **Surface types:**
  - standard, even and odd aspheres, Forbes Q;
  - toroids, Zernike and XY polynomials;
  - diffractive and paraxial surfaces;
  - mirrors of any of these shapes;
  - coordinate breaks;
  - central obscurations and rectangular or elliptical apertures.
- **Multi-configuration (zoom) lenses:** per-configuration values,
  weights and constraints.
- **820 vendor glasses** from the SCHOTT, OHARA, HOYA and CDGM catalog
  files, plus 18 crystals, IR materials, polymers and water from cited
  dispersion formulas.
- **Reference lenses**, reproduced from their published prescriptions:
  - a Cooke triplet;
  - a double Gauss;
  - a Petzval;
  - a phone camera lens with aspheres;
  - the Hubble telescope.

### Optimization

- **Damped least squares** with exact constraints:
  - EFL, BFL, F-number, magnification and track;
  - thicknesses, distortion, chief-ray angle and colour.
- **Merit functions:** transverse ray error or wavefront variance, plus
  weighted operands.
- **Model glasses (nd, νd):** optimized as variables inside the glass
  map, then snapped to real catalog glasses.
- **Global search:** Sobol multi-start over the variables, run in
  parallel.
- **Desensitized optimization:** trades nominal performance against the
  tolerance budget.
- **Glass expert:** substitutes nearby catalog glasses, re-optimizing
  each.

### Analysis

- **Ray tracing:** exact 3D sequential tracing with ray aiming.
  - A compiled kernel (Numba, optional) traces millions of rays per
    second.
  - Paraxial first-order data comes from the same engine.
- **Aberrations:** Seidel sums, ray fans, OPD, field curvature,
  distortion and lateral and axial colour.
- **Image quality:**
  - polychromatic diffraction MTF (FFT and Hopkins), including obscured
    pupils;
  - PSF, encircled energy and Strehl ratio;
  - through-focus MTF and MTF across the field.
- **Physical optics:**
  - polarization ray tracing (Fresnel losses, thin-film coatings,
    diattenuation and retardance pupil maps);
  - Gaussian beams;
  - image simulation.
- **Environment:** temperature and pressure, using glass dn/dT, CTE,
  the air index and housing expansion.
- **Stray light:** double-reflection ghosts traced exactly with the
  coating reflectances.
- **Tolerancing:** sensitivities and the predicted RMS wavefront
  distribution with compensators, checked against exact Monte Carlo;
  also inverse sensitivity.

### Output

- **Code V `.seq` and Zemax `.zmx`:** open and save. Anything a format
  cannot hold is listed.
- **CAD:** STEP solids and IGES surfaces of every element and mirror.
  Spheres are exact; aspheres become B-spline surfaces within 10 nm of
  the true shape.
- **Lens layout:** a 2D section and a 3D view with real rays.
- **Design report:** PDF or HTML, covering the prescription, first
  order, fields, MTF, Seidel, the tolerance budget and drawings.
- **ISO 10110 element drawings:** form and centring codes come from the
  tolerance set.
- **Python scripting API** and an in-app script console for automating
  studies; see [SCRIPTING.md](./SCRIPTING.md).

### AI copilot

- Explains results, suggests design families and verifies claims.
- Every number comes from the engine, and each answer says whether it
  was computed or is a rule of thumb.
- Works offline with a rule-based parser. A local LLM is optional,
  through Ollama or an OpenAI-compatible endpoint.

## Materials catalog

| Source | Count | Examples |
|--------|-------|----------|
| CDGM (catalog 2024-09) | 271 | H-K9L, H-ZF52 |
| HOYA (catalog 2026-04) | 238 | FC5, FCD1, BACD2 |
| SCHOTT (catalog 2025) | 158 | N-BK7, N-SF11, N-LAK33B |
| OHARA (catalog 2025-03) | 134 | S-BSL7, S-LAH51, S-FPL51 |
| Literature | 18 | Fused silica, CaF2, ZnSe, Ge, Si, sapphire, PMMA, water |

Each vendor glass carries what its catalog publishes:

- nd, Vd and the vendor dispersion formula;
- where given: dn/dT constants, CTE, density, conductivity, specific
  heat, Young's modulus, Poisson's ratio, Knoop hardness, internal
  transmittance, status and relative price.

Values a catalog does not give are left empty.

## Project layout

```
├── backend/
│   ├── optics/          # optics engine (no web or UI dependencies)
│   │   ├── raytrace.py      # sequential engine: paraxial + exact rays
│   │   ├── lens_data.py     # the surface-by-surface prescription
│   │   ├── lens_optimize.py, merit.py, global_lens.py, glass_expert.py
│   │   ├── tolerancing.py   # fast tolerancing
│   │   ├── fields.py, mtf_analysis.py, image_quality.py
│   │   ├── polarization_trace.py, environment.py, ghost_trace.py
│   │   ├── reference_lenses.py
│   │   ├── lens_layout.py, lens_report.py
│   │   └── io/              # Code V, Zemax, STEP/IGES, ISO 10110 drawings
│   ├── kestrova/        # Python scripting API
│   ├── api/             # FastAPI endpoints
│   ├── ai/              # AI copilot
│   ├── tests/           # pytest suite (about 1,640 tests)
│   └── kestrova_server.py, kestrova-server.spec   # desktop engine
├── frontend/            # React + TypeScript + Vite interface
├── desktop-app/         # Electron shell
└── .github/workflows/   # tests, lint, desktop builds
```

[ARCHITECTURE.md](./ARCHITECTURE.md) describes how the pieces fit
together.

## Testing

```bash
cd backend && pytest tests/ -q          # backend (CI gate: 80% coverage)
cd frontend && npm test -- --run        # frontend
```

The validation tests compare the engine with independent results:

- vendor and literature refractive indices;
- published lenses (first order, Seidel sums and exact rays against
  ray-optics, designers' focal lengths, the Hubble aplanat);
- the lensmaker equation;
- the Airy pattern and the diffraction-limited MTF;
- Fresnel and thin-film formulas;
- Gaussian beam optics;
- closed-form volumes of the exported CAD solids.

See [TESTING.md](./TESTING.md).

## Documentation

| Document | Contents |
|----------|----------|
| [QUICKSTART.md](./QUICKSTART.md) | Getting it running |
| [USER_GUIDE.md](./USER_GUIDE.md) | Using the app |
| [SCRIPTING.md](./SCRIPTING.md) | Python scripting API, script console, reports and drawings |
| [OPTICS.md](./OPTICS.md) | Conventions, formulas and engine methods |
| [API_REFERENCE.md](./API_REFERENCE.md) | HTTP API |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | How the code is organised |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Developer setup and conventions |
| [TESTING.md](./TESTING.md) | Test suite and validation |
| [CI_CD.md](./CI_CD.md) | Workflows |
| [desktop-app/README.md](./desktop-app/README.md) | Desktop app, builds and signing |
| [CHANGELOG.md](./CHANGELOG.md) | Changes by version |
| [ROADMAP.md](./ROADMAP.md) | Comparison with Code V and the plan to close the gaps |

## Development

Requirements:

- Python 3.11+ (CI also runs 3.12);
- Node.js 18+ (CI runs 18 and 20).

```bash
cd backend && python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

cd frontend && npm install && npm run dev    # http://localhost:5173
```

[DEVELOPMENT.md](./DEVELOPMENT.md) covers conventions, environment
variables and rebuilding the glass catalog.

## License

No license file has been added yet.

## Acknowledgments

- SCHOTT, OHARA, HOYA and CDGM for their published glass catalogs
- M. Hayford's [ray-optics](https://github.com/mjhoptics/ray-optics), whose
  printed results validate the reference lenses
- W. T. Welford, *Aberrations of Optical Systems*
- W. J. Smith, *Modern Optical Engineering*
- M. Born and E. Wolf, *Principles of Optics*
- E. Hecht, *Optics*
