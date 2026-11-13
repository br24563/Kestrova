# Architecture

## Principles

1. **The engine stands alone.** `backend/optics` has no web or UI
   dependencies. The API, the scripting API, the AI layer and the tests
   all use it the same way.
2. **SI units inside.** The engine works in metres and radians. Unit
   conversion happens only at the edges: the interface converts for
   display, and CAD files are written in millimetres.
3. **Independent validation.** Every result is checked against something
   the engine did not compute: published designs, closed forms, vendor
   data or another program. The engine is never checked against itself.
4. **Stateless API.** Each request carries the whole lens or system and
   gets results back. The backend keeps no session state (saved projects
   aside).

## Overview

```
┌──────────────────────────── Desktop app (Electron) ────────────────────────────┐
│  starts kestrova-server on a free local port, waits for KESTROVA_PORT=<port>,  │
│  opens the interface it serves; saves PDFs (printToPDF) for the Report tab     │
└────────────────────────────────────────┬───────────────────────────────────────┘
                                         │
┌─────────────── Frontend (React + TypeScript + Vite, frontend/src) ─────────────┐
│ App.tsx: header, component editor, Lens Data Editor, optical bench,            │
│          analysis tabs, right panel                                            │
│ components/lens      Lens Data Editor, surface details, configurations,        │
│                      merit, constraints, optimize, global search, glass expert,│
│                      tolerancing                                               │
│ components/analysis  layout, ray fan, OPD, MTF, PSF, polarization,             │
│                      environment, beam, image simulation, ghosts               │
│ components/report    design report, ISO 10110 drawings                         │
│ components/script    script console                                            │
│ api.ts (fetch client), types.ts (mirrors the engine's models)                  │
└────────────────────────────────────────┬───────────────────────────────────────┘
                                         │ HTTP / JSON
┌──────────────────────── Backend (FastAPI, backend/api/main.py) ────────────────┐
│ /api/lens/*      prescription: resolve, optimize, global search, tolerance,    │
│                  merit, configurations, environment, layout, report, drawings, │
│                  import/export (.seq, .zmx, STEP, IGES), samples               │
│ /api/analyze/*   analyses of a component system (ray fans, MTF, PSF, fields,   │
│                  polarization, ghosts, beams, imaging, ...)                    │
│ /api/script/*    script console (loopback pages only)                          │
│ /api/ai/*        AI copilot             /api/systems  saved projects (SQLite)  │
└──────┬──────────────────────────┬────────────────────────────┬─────────────────┘
       │                          │                            │
┌──────┴───────────┐  ┌───────────┴───────────┐  ┌─────────────┴──────────────┐
│ backend/kestrova │  │ backend/ai            │  │ backend/persistence.py     │
│ scripting API    │  │ copilot: structured   │  │ projects in SQLite         │
│ and script runner│  │ commands, providers   │  │ ($KESTROVA_DATA_DIR)       │
└──────┬───────────┘  └───────────┬───────────┘  └────────────────────────────┘
       └────────────┬─────────────┘
┌───────────────────┴──────── Optics engine (backend/optics) ────────────────────┐
│ lens_data.py   LensData: the surface-by-surface prescription; resolve          │
│                (solves, pickups, apertures), configurations, to_system         │
│ models.py      OpticalSystem: components along the axis (lenses, surfaces,     │
│                mirrors, stops, aspheres, ...)                                  │
│ raytrace.py    the sequential engine: Sequence, paraxial first order, exact    │
│                3D tracing with ray aiming, OPD     (_fasttrace.py: Numba kernel)│
│ analyses       fields, mtf_analysis, image_quality, seidel, merit,             │
│                polarization_trace, environment, ghost_trace, beam_lens,        │
│                imaging, lens_layout                                            │
│ design         lens_optimize, global_lens, glass_expert, tolerancing           │
│ data           materials (+ data/ vendor catalogs), reference_lenses           │
│ io/            lensfile (Code V, Zemax), cad_export (STEP, IGES),              │
│                element_drawing (ISO 10110); lens_report.py (HTML report)       │
└────────────────────────────────────────────────────────────────────────────────┘
```

## The two system models

- **`OpticalSystem`** (`models.py`): components at positions along the
  axis. It covers thin lenses, thick lenses, spherical and aspheric
  surfaces, mirrors, stops and the advanced surface types. The component
  editor and the `/api/analyze/*` endpoints work on it. It is mirrored
  in `frontend/src/types.ts`.
- **`LensData`** (`lens_data.py`): one row per surface, as in Code V or
  Zemax. Each row has its type, radius, thickness, material, semi-diameter
  and terms, plus its solves, pickups and variables. On top of the rows
  sit the field table, wavelengths and weights, configurations,
  constraints and the merit function.

`lens_data.resolve()` applies the solves and pickups and fills automatic
semi-diameters. `to_system()` then builds the equivalent
`OpticalSystem`, so every analysis is written once and serves both.

`raytrace.build_sequence()` turns an `OpticalSystem` into the `Sequence`
that everything traces: surfaces with shapes, frames, indices and
apertures. Every surface type runs in the compiled kernel when Numba is
installed. Without it they take the NumPy path, which gives identical
results.

## Adding a surface type

1. Add the shape to `raytrace.py` (sag, normal, intersection), or to
   `advanced_surfaces.py` as a component. Give it an analytic gradient,
   then add it to `_fasttrace.py` (`supports`, `_pack`, `_sag_grad_impl`)
   and to the systems in `tests/test_fasttrace.py`. Until then a lens
   that uses it is traced by NumPy.
2. Add the row fields to `LensSurface` and map them in
   `lens_data._shaped_component` / `surface_shape`.
3. Read and write it in `io/lensfile.py` where Code V or Zemax can hold
   it (otherwise the writers list it in their warnings).
4. Add it to `SurfaceDetails.tsx` and `types.ts`.
5. Test it against a closed form or published result.

## Scripting and the console

`backend/kestrova` wraps the engine in a `Lens` class (see
[SCRIPTING.md](./SCRIPTING.md)).

The Script tab posts code to `/api/script/run`. `kestrova/runner.py` runs
it in a freshly spawned process with a time limit, and returns the
printed output, the traceback and the resulting lens. The endpoint
refuses any request that does not come from this computer: it checks
the client address, the Host header (against DNS rebinding) and the
Origin (so other web sites cannot post scripts).

## AI layer

The language model never computes optics. It emits structured commands
(`ai/commands.py`). `ai/engine.py` validates them and applies them to the
engine, and the results are explained from the engine's own numbers.

The providers (`ai/providers.py`) are a rule-based offline parser,
Ollama, or any OpenAI-compatible endpoint.

## Desktop app

`desktop-app/electron/main.js` starts the bundled engine
(`backend/kestrova_server.py`, frozen by PyInstaller with
`kestrova-server.spec`) with `--port 0 --parent-pid <pid>`. Then it:

- waits for the engine to print `KESTROVA_PORT=<port>`;
- loads the interface the engine serves from that port;
- passes `KESTROVA_DATA_DIR` (the app's user-data folder) for projects,
  the log and the Numba kernel cache.

The engine exits with the app. Once listening, it loads the cached
kernels in a background thread.

## Sign convention

- Light travels left to right along +z, and heights are positive above
  the axis.
- A radius is positive when its centre of curvature is to the right.
- Thicknesses are signed and turn negative after a mirror.
- Distances to the left are negative, so a real object in front of a lens
  has s < 0 and magnification is m = s'/s.

See [OPTICS.md](./OPTICS.md).
