# Development Guide

## Setup

Requirements:

- Python 3.11+ (CI runs 3.11 and 3.12; the desktop build uses 3.12);
- Node.js 18+ (CI runs 18 and 20).

```bash
# backend
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt   # Numba is optional and skipped on Intel Macs

# frontend
cd ../frontend
npm install
```

## Running

```bash
cd backend && uvicorn api.main:app --reload --port 8000   # API, docs at /docs
cd frontend && npm run dev                                  # http://localhost:5173
```

Vite proxies `/api` to port 8000.

The desktop shell runs against the dev server with
`cd desktop-app && npm ci && npm run dev`. It starts the backend from
source with the Python on `PATH`, or `$KESTROVA_PYTHON` if that is set.
Building installers is covered in
[desktop-app/README.md](./desktop-app/README.md).

## Checks

These are the same checks CI runs (see [CI_CD.md](./CI_CD.md)):

```bash
cd backend
pytest tests/ -q --cov=optics --cov-fail-under=80
black --check optics/ ai/ api/
flake8 optics/ ai/ api/ --select=E9,F63,F7,F82
mypy optics/ --ignore-missing-imports

cd ../frontend
npm test -- --run
npx eslint src
npx prettier --check "src/**/*.{ts,tsx,css}"
npx tsc --noEmit
```

The full backend suite takes several minutes, because the tolerancing,
global-search and Monte Carlo tests trace millions of rays. While working
on one area, run its file, e.g. `pytest tests/test_cad_layout.py`.

## Environment variables

| Variable | Effect |
|----------|--------|
| `KESTROVA_DATA_DIR` | Folder for saved projects (SQLite), and in the desktop app the engine log and Numba cache. Default: `backend/` when run from source; the platform's user-data folder (`%APPDATA%\Kestrova`, `~/Library/Application Support/Kestrova`, `~/.local/share/kestrova`) in the desktop app |
| `KESTROVA_FRONTEND_DIR` | Built interface for the backend to serve (default: the bundled copy in the desktop app, else `frontend/dist`) |
| `KESTROVA_DISABLE_SCRIPTING` | Any value turns the script console's `/api/script/run` off |
| `KESTROVA_PYTHON` | Python the desktop shell uses to run the backend in development |
| `OPTICS_NO_NUMBA` | Any value turns the compiled ray trace off (the NumPy path gives the same results) |
| `NUMBA_CACHE_DIR` | Where Numba caches compiled kernels. The frozen engine sets it to `$KESTROVA_DATA_DIR/numba-cache` |
| `AI_ENABLED` | `false` keeps the copilot on its rule-based parser |
| `AI_PROVIDER` | `auto` (default), `ollama`, `openai` (any OpenAI-compatible endpoint) or `mock` |
| `AI_MODEL`, `AI_BASE_URL`, `AI_API_KEY`, `AI_TIMEOUT_S` | Model, endpoint, key and timeout for the provider (`OLLAMA_MODEL` and `OLLAMA_URL` are accepted too) |

For a local LLM:

```bash
ollama pull llama3.2
export AI_PROVIDER=ollama AI_MODEL=llama3.2
```

## Conventions

- **Units:** the engine uses SI units throughout (m, rad). Convert only
  at the interface and in file formats.
- **Validation:** a test compares the engine with something independent
  (a closed form, a published value, vendor data or another program),
  never with the engine's own formulas. If a test and the code disagree,
  find out which is right before changing either.
- **Python:** type hints, docstrings that say what the function computes
  and in what units, formatted with black. `mypy optics/` must pass.
- **TypeScript:** strict mode, Prettier formatting. API calls go in
  `src/api.ts`, and shared types in `src/types.ts` (they mirror the
  engine's Pydantic models).
- **Tests next to the code:** frontend tests sit beside their components
  (`*.test.tsx`); backend tests are in `backend/tests/`, one file per
  area.
- **Documentation:** a new feature updates the relevant docs.
  - Always: CHANGELOG.md and USER_GUIDE.md.
  - New endpoints: API_REFERENCE.md.
  - New methods: OPTICS.md.
  - New scripting calls: SCRIPTING.md.

## Rebuilding the glass catalog

`backend/tools/build_glass_catalog.py` regenerates
`backend/optics/data/glass_catalog.json` from the vendors' Excel catalog
files. It needs `openpyxl`.

## Workflow

1. Work on a branch; `master` is protected and changes arrive by pull
   request.
2. Change the engine and add a test against an independent reference.
3. Run the checks above.
4. Update the interface and the documentation.
5. Open a pull request. CI runs the tests on Linux, Windows and macOS,
   the linters, and the desktop builds when packaging changes.
