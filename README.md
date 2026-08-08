# AI Optical Design Engineer

A free, local-first optical engineering application for designing, simulating, and analyzing simple optical systems.

## Overview

AI Optical Design Engineer is an educational tool that allows users to construct optical systems (object → lenses → image plane), trace rays through them, and analyze optical properties such as focal length, magnification, F-number, and numerical aperture.

The application runs entirely on your local machine — no cloud services, no paid APIs, no subscriptions.

## Features (MVP)

- **Two-lens optical system designer** — Add, remove, and edit thin lenses
- **Paraxial ray tracing** — Trace chief, marginal, and fill rays through the system
- **Optical analysis** — Effective focal length, magnification, F-number, NA, RMS spot radius
- **Spot diagram** — Visualize where rays converge at the image plane
- **Interactive optical bench** — SVG visualization with zoom/pan
- **Unit system** — Supports nm, μm, mm, cm, m, degrees with centralized conversion
- **RESTful API** — FastAPI backend with JSON endpoints

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- npm

### Running the Application

1. **Start the backend** (FastAPI):

   ```bash
   cd backend
   source venv/bin/activate  # or activate your virtualenv
   uvicorn api.main:app --reload --port 8000
   ```

2. **Start the frontend** (Vite dev server):

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. Open `http://localhost:5173` in your browser.

### Running Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

## Project Structure

```
ai-optical-design-engineer/
├── backend/
│   ├── api/
│   │   └── main.py          # FastAPI REST API
│   ├── optics/
│   │   ├── units.py          # Unit conversion system
│   │   ├── models.py         # Data models (Pydantic)
│   │   ├── lenses.py         # Thin lens math + ABCD matrices
│   │   ├── surfaces.py       # Spherical surface calculations
│   │   ├── rays.py           # Ray tracing engine
│   │   ├── systems.py        # System assembly & management
│   │   ├── materials.py      # Refractive index data
│   │   └── analysis.py       # Optical analysis calculations
│   ├── tests/                # pytest test suite (119 tests)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Main React component
│   │   ├── api.ts            # API client
│   │   ├── types.ts          # TypeScript type definitions
│   │   └── components/
│   │       ├── OpticalBench.tsx
│   │       ├── ComponentEditor.tsx
│   │       ├── AnalysisPanel.tsx
│   │       └── SpotDiagram.tsx
│   └── package.json
├── ARCHITECTURE.md
├── DEVELOPMENT.md
├── OPTICS.md
└── TESTING.md
```

## License

This project is educational and experimental. See the proposal document for details.
