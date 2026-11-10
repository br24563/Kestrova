# CI/CD

GitHub Actions runs four kinds of checks. `master` is protected: changes
arrive through pull requests, which must pass the tests and lint.

## Test Suite (`.github/workflows/test.yml`)

Runs on pushes and pull requests to `master` (and `main`).

| Job | What it does |
|-----|--------------|
| backend-tests | Runs pytest with coverage on Ubuntu (Python 3.11 and 3.12), Windows and macOS (3.12). Fails below 80% coverage of `optics/`, a ratchet that is raised as tests are added. A failing platform does not cancel the others. Uploads the coverage report |
| frontend-tests | Runs Vitest and the production build on Node 18 and 20. Uploads the build |
| integration-tests | After both pass: starts the backend, runs `tests/test_workflows.py` and calls the health and default-system endpoints |

## Lint and Format (`.github/workflows/lint.yml`)

- **Backend:**
  - `flake8` (syntax errors and undefined names);
  - `black --check` on `optics/ ai/ api/`;
  - `mypy optics/`.
- **Frontend:** ESLint and Prettier.

## Desktop builds (`.github/workflows/desktop.yml`)

Builds the installers on Windows, macOS on Apple Silicon (`macos-15`) and
macOS on Intel (`macos-15-intel`):

1. Build the web interface.
2. Freeze the backend with PyInstaller (`backend/kestrova-server.spec`).
3. Smoke-test the frozen engine: it must start, answer `/api/health` and
   serve the interface.
4. Package with electron-builder. The build is signed when the signing
   secrets exist: Azure Trusted Signing or a certificate file on Windows,
   and a Developer ID certificate with notarization on macOS.
5. Verify the signatures of signed builds: signtool on Windows, codesign
   and Gatekeeper on macOS.
6. Write a `.sha256` checksum for each installer, and upload them all as
   run artifacts.

It runs on version tags `v*` (and then publishes a GitHub Release with
the installers), by hand from the Actions tab, and on pull requests that
change the packaging (`desktop-app/`, the server entry point or spec,
`requirements.txt`, the workflow).

The secret names and how to obtain certificates are in
[desktop-app/README.md](./desktop-app/README.md#signing-optional).

## Dependabot (`.github/dependabot.yml`)

Weekly update pull requests for the Python packages (`backend/`), the npm
packages (`frontend/`) and the Actions versions.

## Releasing

1. Move the `[Unreleased]` entries in CHANGELOG.md under the new version.
2. Raise the version in `backend/optics/__init__.py` (`__version__`),
   `frontend/package.json` and `desktop-app/package.json`, and in the
   README badge.
3. Merge to `master`, then tag it:
   `git tag v0.5.0 && git push origin v0.5.0`.
4. The desktop workflow builds, verifies and publishes the release.

## When CI fails

- **Tests fail in CI but pass locally:**
  - check the Python and Node versions;
  - check new packages are in `requirements.txt` or `package.json`;
  - check for platform differences (paths, line endings, float
    round-off on another BLAS).
- **Coverage below the gate:** run
  `pytest tests/ --cov=optics --cov-report=term-missing` and test the
  uncovered lines.
- **Lint:** run the commands in
  [DEVELOPMENT.md](./DEVELOPMENT.md#checks) locally. On Windows, Prettier
  reports files checked out with CRLF line endings; CI checks out LF, so
  those warnings do not appear there.
- **Desktop build:** the smoke test prints the frozen engine's log.
  Missing modules usually mean a package now imports something
  dynamically. Add it to `hiddenimports` in `kestrova-server.spec`.
