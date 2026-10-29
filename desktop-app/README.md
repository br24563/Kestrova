# Kestrova desktop app

An Electron shell around the optics engine. On launch it starts the bundled
backend (`kestrova-server`, the Python backend frozen with PyInstaller) on a
free local port, waits for it, and opens the web interface the backend
serves. The engine exits with the app: it watches the app's process, so
this holds even if the app crashes.

- Projects and the engine log (`backend.log`) are kept in the app's
  user-data folder: `%APPDATA%\Kestrova` on Windows,
  `~/Library/Application Support/Kestrova` on macOS.
- Nothing needs to be installed besides the app: the engine includes its own
  Python, NumPy, SciPy and Numba.

## Downloads

Installers are built by the `Desktop builds` workflow
(`.github/workflows/desktop.yml`) on real Windows and macOS machines. Push a
version tag (`git tag v0.3.0 && git push origin v0.3.0`) to publish them on
the repository's Releases page; the workflow can also be run by hand from
the Actions tab, and the installers are then attached to the run.

| Platform | File |
|---|---|
| Windows 10/11 (x64) | `Kestrova-<version>-win-x64.exe` |
| macOS, Apple Silicon | `Kestrova-<version>-mac-arm64.dmg` |
| macOS, Intel | `Kestrova-<version>-mac-x64.dmg` |

### Unsigned builds

Until signing certificates are added (below), the installers are unsigned:

- **Windows** shows a SmartScreen warning: choose *More info*, then
  *Run anyway*.
- **macOS** refuses to open the app at first: right-click it in
  Applications, choose *Open*, then *Open* again (or allow it in System
  Settings → Privacy & Security).

## Building on your own machine

Each platform must be built on that platform (the frozen engine is native
code). Needs Python 3.12 and Node.js 20.

```bash
cd frontend && npm ci && npm run build            # the web interface
cd ../backend && pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean kestrova-server.spec   # -> backend/dist/kestrova-server
cd ../desktop-app && npm ci
npx electron-builder --win    # or --mac; output in desktop-app/dist-electron
```

On Windows without Developer Mode, add `-c.win.signAndEditExecutable=false`
(electron-builder's signing tools need permission to create symbolic links);
the executable then lacks its embedded icon and version information.

## Development

```bash
cd desktop-app && npm ci && npm run dev
```

This starts the Vite dev server and the app; the app runs the backend from
source on port 8000 with the Python on `PATH` (or `$KESTROVA_PYTHON`).

## Signing (optional)

Add these repository secrets and the workflow signs the builds:

- **macOS** (needs an Apple Developer account): `MAC_CERT_P12` (a base64
  Developer ID Application certificate), `MAC_CERT_PASSWORD`, and for
  notarization `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`.
- **Windows**: `WIN_CERT_P12` (a base64 code-signing certificate) and
  `WIN_CERT_PASSWORD`.

The icon is drawn by `tools/make_icon.py` (`assets/icon.png`;
electron-builder derives the `.ico` and `.icns` from it).
