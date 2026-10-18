# AI Optical Design Engineer

[![Version](https://img.shields.io/badge/version-0.2.0-orange)](./CHANGELOG.md)

A free, local-first optical design application for designing, simulating and
analyzing optical systems, with a Python engine, a FastAPI backend and a
React frontend.

## 🚀 Quick Start

### Option 1: One-Click Launcher

```bash
# Linux / Mac
./launch.sh

# Windows
launch.bat
```

### Option 2: Manual Setup

See [QUICKSTART.md](./QUICKSTART.md) for detailed instructions.

### Desktop app

An Electron wrapper lives in [desktop-app/](./desktop-app/README.md). No
prebuilt installers are published yet; build it from source.

---

## ✨ Features

### Optical Design
- **820 vendor glasses** read from the SCHOTT, OHARA, HOYA and CDGM catalog
  files, plus 18 crystals, IR materials, polymers and water from cited
  literature dispersion formulas
- Ideal (paraxial) thin lenses, thick lenses, spherical surfaces, mirrors
  (spherical and conic), aperture stops
- Aspheres (even, odd, Forbes Q), Zernike, toroidal and diffractive surfaces,
  coordinate breaks
- Preset systems derived from first-order optics (telescopes, microscope,
  relay, achromat, paraboloid)

### Analysis
- **Ray tracing**: exact 3D sequential real-ray tracing with ray aiming, plus
  a paraxial first-order trace (EFL, BFL, pupils, Lagrange invariant)
- **Aberrations**: Seidel sums and third-order aberrations, checked against
  exact real-ray measures; ray fans, OPD maps, Zernike fits
- **Diffraction**: FFT PSF and MTF from the real wavefront, Strehl ratio,
  encircled energy, diffraction-limit (Maréchal) test
- **Chromatic**: longitudinal and lateral colour
- **Spot diagrams**: real-ray 2D spots
- **Illumination**: vignetting and relative illumination from the projected
  solid angle of the real ray bundle

### Optimization
- Global search (differential evolution, particle swarm) and local
  refinement (damped least squares on residuals, L-BFGS-B)
- Constraints: edge and centre thickness, air gaps, EFL, BFL, distortion
- Tolerance-aware (high-yield) optimization and Pareto fronts

### Tolerance Analysis
- Monte Carlo with errors added to nominal values; decenters and tilts as
  exact coordinate-break pairs
- Sensitivity ranking, focus and air-space compensators, yield and Cpk

### Stray Light
- Ghost reflections traced with real rays
- First-order point source transmittance (PST) and narcissus (YNI)

### AI Copilot
- Explain results, suggest design families, and verify claims; every number
  comes from the optics engine, and answers state whether they were computed
  or are rules of thumb
- Optional local LLM through Ollama or an OpenAI-compatible endpoint

### Import/Export
- **Zemax** .ZMX and **Code V** .SEQ import/export of sequential
  prescriptions (ideal thin lenses export to Zemax as paraxial surfaces;
  Code V has no equivalent, so they are refused)
- **CAD**: STL, OBJ and PLY meshes of the lens elements (STEP and IGES are
  not supported)
- **Drawings**: SVG lens drawings and ISO 10110 drawings (tolerances only
  when you supply them)
- **BOM**: element list with vendor glass and mass from vendor density
  (no cost estimates: prices are not published)
- **Sag tables** and Markdown engineering reports

---

## 📊 Materials Catalog

| Source | Count | Examples |
|--------|-------|----------|
| CDGM (catalog 2024-09) | 271 | H-K9L, H-ZF52 |
| HOYA (catalog 2026-04) | 238 | FC5, FCD1, BACD2 |
| SCHOTT (catalog 2025) | 158 | N-BK7, N-SF11, N-LAK33B |
| OHARA (catalog 2025-03) | 134 | S-BSL7, S-LAH51, S-FPL51 |
| Literature | 18 | Fused silica, CaF2, ZnSe, Ge, Si, sapphire, PMMA, water |

Each vendor glass carries what its catalog publishes: nd, Vd, the vendor
dispersion formula, and where given dn/dT constants, CTE, density,
conductivity, specific heat, Young's modulus, Poisson's ratio, Knoop
hardness, internal transmittance, status and relative price. Values a
catalog does not give are left empty.

---

## 🏗️ Architecture

```
├── backend/                 # Python FastAPI backend
│   ├── optics/             # Core optical engine
│   │   ├── raytrace.py     # Sequential engine (paraxial + real rays)
│   │   ├── pupil.py        # Wavefront, PSF, MTF, Strehl
│   │   ├── materials.py    # Glass and material data
│   │   ├── data/           # Vendor glass catalog (JSON)
│   │   ├── optimization.py, advanced_optimization.py
│   │   ├── tolerance.py
│   │   ├── nonsequential.py, ghost.py   # Stray light
│   │   └── io/             # Zemax, Code V, drawings, BOM
│   ├── tools/              # Catalog builder
│   ├── ai/                 # AI copilot
│   ├── api/                # FastAPI endpoints
│   └── tests/
├── frontend/               # React/TypeScript frontend
├── desktop-app/            # Electron desktop app
├── launch.sh / launch.bat  # Launchers
└── .github/workflows/      # CI
```

Several frontend components (design comparison, ghost analysis, merit
function editor, prescription editor, report generator, ray fan and OPD
plots and others in `frontend/src/components`) are written but not yet
wired into the app.

---

## 🧪 Testing

```bash
cd backend
pytest tests/ -q
```

The validation tests compare the engine with results computed
independently: vendor and literature refractive indices, the thick-lens
lensmaker equation, exact defocus geometry, the Airy pattern and the
diffraction-limited MTF, the exact off-axis irradiance of a disk, and
third-order aberrations against real rays. See [TESTING.md](./TESTING.md).

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](./QUICKSTART.md) | Quick start guide |
| [USER_GUIDE.md](./USER_GUIDE.md) | User guide |
| [OPTICS.md](./OPTICS.md) | Conventions, formulas and engine methods |
| [API_REFERENCE.md](./API_REFERENCE.md) | API documentation |
| [TESTING.md](./TESTING.md) | Testing guide |
| [CI_CD.md](./CI_CD.md) | CI/CD documentation |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Architecture overview |
| [desktop-app/README.md](./desktop-app/README.md) | Desktop app docs |

---

## 🛠️ Development

### Prerequisites
- Python 3.11+
- Node.js 18+

### Setup
```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### Running
```bash
# Terminal 1: Backend
cd backend
uvicorn api.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

### Rebuilding the glass catalog
`backend/tools/build_glass_catalog.py` regenerates
`backend/optics/data/glass_catalog.json` from the vendors' Excel files
(requires `openpyxl`).

---

## 🤖 AI Integration

Optional local LLM through Ollama:

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.2

export AI_PROVIDER=ollama          # or "auto" (default)
export OLLAMA_MODEL=llama3.2
export OLLAMA_URL=http://localhost:11434
```

Set `AI_ENABLED=false` to use only the built-in rule-based parser.

---

## 📈 Roadmap

- Wire the remaining frontend components into the app
- Polarization and coatings in the sequential image-quality analyses
- Multi-configuration optimization in the UI
- STEP/IGES export through a CAD kernel
- PDF report generation

---

## 📄 License

No license file has been added yet.

---

## 🙏 Acknowledgments

- SCHOTT, OHARA, HOYA and CDGM for their published glass catalogs
- W. T. Welford, *Aberrations of Optical Systems*
- W. J. Smith, *Modern Optical Engineering*
- M. Born and E. Wolf, *Principles of Optics*
- E. Hecht, *Optics*
