# Architecture

## Design Principles

1. **Separation of concerns**: The core optics engine is independent of the UI. It can be used from Python directly, through the FastAPI backend, or in future CLI tools.
2. **Simplicity over cleverness**: Modules are kept small and readable. Each file has a single responsibility.
3. **Scientific correctness**: All calculations use SI base units internally (meters, radians). Unit conversions happen only at the boundary (UI input → API → engine).
4. **Testability**: Mathematical functions are pure and easily testable with known physical cases.
5. **Extensibility**: The component architecture uses a discriminated union pattern, making it easy to add new optical component types.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                Frontend (React)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │Component │ │Optical   │ │Analysis  │ │Spot     │ │
│  │Editor    │ │Bench     │ │Panel     │ │Diagram  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘ │
│       │            │            │            │      │
│       └────────────┴────────────┴────────────┘      │
│                        │                              │
│                   { API calls via fetch }             │
└────────────────────────┼──────────────────────────────┘
                         │ HTTP/JSON
┌────────────────────────┴──────────────────────────────┐
│                Backend (FastAPI)                      │
│  ┌──────────────────────────────────────┐           │
│  │  api/main.py                         │           │
│  │  - GET  /api/system/default         │           │
│  │  - POST /api/trace                  │           │
│  │  - POST /api/analyze                │           │
│  │  - POST /api/validate               │           │
│  └──────────┬───────────────────────────┘            │
│             │ Python imports                         │
└─────────────┼───────────────────────────────────────┘
              │
┌─────────────┴───────────────────────────────────────┐
│           Core Optics Engine (optics/)              │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        │
│  │ units.py │ models.py │ lenses.py │ rays.py │     │
│  │          │ surfaces │ systems │ analysis │    │
│  │          │ materials │         │          │    │
│  └────────┘ ┌────────┘ ┌────────┘ ┌────────┘    │
│             │          │          │              │
│  All modules use SI base units (meters, radians)  │
└───────────────────────────────────────────────────┘
```

## Component Layers

### Layer 1: Core Optics Engine (`backend/optics/`)

The optics engine is a pure Python library with zero dependencies on the web framework or UI. Each module has a specific role:

| Module | Responsibility |
|--------|---------------|
| `units.py` | Centralized unit conversions (nm, mm, cm, m, degrees → meters/radians) |
| `models.py` | Pydantic data models for all optical components, rays, and results |
| `lenses.py` | Thin lens equations, ABCD matrix method, F-number, NA |
| `surfaces.py` | Spherical refractive surface math (Phase 2 ready) |
| `rays.py` | Ray generation, propagation, tracing through systems, spot diagram |
| `systems.py` | System creation, component management (add/remove/update), validation |
| `materials.py` | Refractive index database and Sellmeier equation support |
| `analysis.py` | Full system analysis (EFL, magnification, distances, NA, F/#) |

### Layer 2: API Layer (`backend/api/`)

FastAPI REST API that wraps the optics engine. The API is **stateless** — the frontend sends the complete optical system with each request, and the backend returns results. This keeps the backend simple and scalable.

### Layer 3: Frontend (`frontend/`)

React application built with Vite and TypeScript. Uses Tailwind CSS for styling.

## Data Model

The optical system is represented by `OpticalSystem` (Pydantic model in `models.py`, mirrored as TypeScript interfaces in `types.ts`):

```
OpticalSystem
├── components: list[OpticalComponent]  (discriminated by "type" field)
│   ├── ThinLens (type: "thin_lens")
│   ├── SphericalSurface (type: "spherical_surface")
│   ├── ApertureStop (type: "aperture")
│   └── Mirror (type: "mirror")
├── wavelengths: list[float]  (meters, default: 550e-9 = 550nm)
├── object: Object (position, height, orientation)
├── image_plane: ImagePlane (position)
└── analysis_settings: AnalysisSettings (num_rays, ray_types, etc.)
```

### Component Extensibility

New component types can be added by:
1. Creating a new Pydantic model in `models.py` with a `type: Literal["..."]` discriminator
2. Adding it to the `OpticalComponent` union
3. Handling it in `rays.py` (ray tracing) and `analysis.py` (analysis)
4. Adding TypeScript interface to `frontend/src/types.ts`

## Sign Convention

The project uses the **Cartesian sign convention**:

- Light travels from left to right (z-axis)
- Heights above the optical axis are positive (y-axis)
- Angles measured counterclockwise from the axis are positive
- Object distance (s): positive if object is to the left of the lens
- Image distance (s'): positive if image is to the right of the lens
- Focal length (f): positive for converging lenses, negative for diverging

## AI Architecture (Future)

When AI is added, the LLM will never perform calculations directly. Instead:

```
User (natural language)
    ↓
LLM generates structured command (validated JSON)
    ↓
App validates & applies command to optics engine
    ↓
Optics engine performs calculation
    ↓
LLM explains results to user
```

This ensures all numerical results come from the validated engine, not from LLM-generated math.
