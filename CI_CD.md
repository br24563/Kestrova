# CI/CD Pipeline Documentation

## Overview

This project uses GitHub Actions for continuous integration and continuous deployment.

## Workflows

### 1. Test Suite (`.github/workflows/test.yml`)

Runs on every push and pull request to main/master branches.

**Jobs:**
- **backend-tests**: Tests Python backend across Python 3.11 and 3.12
  - Runs all pytest tests
  - Generates coverage report (minimum 80%)
  - Uploads coverage artifact

- **frontend-tests**: Tests React frontend across Node 18 and 20
  - Runs Vitest tests
  - Builds production bundle
  - Uploads build artifact

- **integration-tests**: Runs after backend and frontend tests pass
  - Starts backend server
  - Runs workflow integration tests
  - Tests API endpoints

**Triggers:**
- Push to main/master
- Pull requests to main/master

### 2. Lint and Format (`.github/workflows/lint.yml`)

Runs code quality checks.

**Backend:**
- flake8: Linting for syntax errors and style
- black: Code formatting check
- mypy: Type checking

**Frontend:**
- ESLint: Linting for TypeScript/React
- Prettier: Code formatting check

### 3. Release (`.github/workflows/release.yml`)

Creates releases when tags are pushed.

**Steps:**
1. Run all tests
2. Build frontend
3. Create release archive
4. Create GitHub Release
5. Upload release asset

**Trigger:** Push tags matching `v*`

### 4. Dependabot (`.github/dependabot.yml`)

Automated dependency updates.

- **pip**: Weekly checks for Python dependencies
- **npm**: Weekly checks for Node.js dependencies
- **github-actions**: Weekly checks for action versions

## Status Badges

Add to README.md:

```markdown
![Tests](https://github.com/USERNAME/ai-optical-design-engineer/workflows/Test%20Suite/badge.svg)
![Lint](https://github.com/USERNAME/ai-optical-design-engineer/workflows/Lint%20and%20Format/badge.svg)
```

## Running Tests Locally

### Backend

```bash
cd backend
source venv/bin/activate
pytest tests/ -v                    # Run all tests
pytest tests/ --cov=optics         # With coverage
pytest tests/test_edge_cases.py -v  # Specific test file
```

### Frontend

```bash
cd frontend
npm test -- --run               # Run all tests
npm run build                    # Build for production
```

## Deployment

### Manual Deployment

1. Create a virtual environment:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Start the backend:
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```

3. Start the frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

### Docker Deployment (Future)

```dockerfile
# Backend
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Frontend
FROM node:20-alpine
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
CMD ["npm", "run", "preview"]
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_ENABLED` | Enable Ollama AI | `false` |
| `OLLAMA_MODEL` | Ollama model name | `llama3.2` |
| `OLLAMA_URL` | Ollama server URL | `http://localhost:11434` |

## Monitoring

- GitHub Actions dashboard for CI/CD status
- Code coverage reports via artifacts
- Release notes in GitHub Releases

## Troubleshooting

### Tests Fail in CI but Pass Locally

1. Check Python/Node version matches
2. Verify all dependencies are in requirements.txt/package.json
3. Check for environment-specific code

### Coverage Below Threshold

1. Run `pytest --cov=optics --cov-report=html`
2. Open `htmlcov/index.html` to see uncovered lines
3. Add tests for uncovered code

### Build Failures

1. Check for TypeScript errors: `npx tsc --noEmit`
2. Check for lint errors: `npx eslint src/`
3. Verify all imports are correct
