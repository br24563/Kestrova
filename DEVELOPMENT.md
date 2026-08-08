# Development Guide

## Setup

### Backend (Python)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend (React/TypeScript)

```bash
cd frontend
npm install
```

## Running the Application

### Backend API

```bash
cd backend
source venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

### Frontend Dev Server

```bash
cd frontend
npm run dev
```

The app will be available at `http://localhost:5173`. Vite proxies `/api` requests to the backend automatically.

### Frontend Production Build

```bash
cd frontend
npm run build
```

Output goes to `frontend/dist/`.

## Testing

### Backend Tests (pytest)

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

### Frontend Tests (Vitest)

```bash
cd frontend
npm run test
```

## Project Conventions

### Code Style

- **Python**: Follow PEP 8. Use type hints. Keep functions small and focused.
- **TypeScript**: Use strict mode. Type all function parameters and return values.
- **Comments**: Write docstrings for all public functions. Explain *why*, not *what*.
- **Tests**: Write tests for all mathematical functions with known physical cases.

### File Organization

- One concept per file. Keep files under ~300 lines.
- Backend: `backend/optics/` for core engine, `backend/api/` for API, `backend/tests/` for tests.
- Frontend: `src/components/` for UI components, `src/api.ts` for API client, `src/types.ts` for types.

### Commits

- Write descriptive commit messages.
- Make small, focused commits.
- Do not commit `venv/`, `node_modules/`, or generated files.

## Development Workflow

1. Write or modify a function in the optics engine.
2. Add/update tests with known physical cases.
3. Run tests: `pytest tests/ -v`.
4. If tests fail, fix the implementation (not the tests).
5. Update the frontend if needed.
6. Commit with a descriptive message.
