# Quick Start

## Desktop app

The simplest way to run Kestrova is the desktop installer from the
repository's Releases page (Windows, and macOS on Apple Silicon or
Intel). It bundles the optics engine, so nothing else needs installing.

Until the builds are signed, the system asks for confirmation the first
time:

- **Windows:** in SmartScreen, choose *More info*, then *Run anyway*.
- **macOS:** right-click the app and choose *Open*.

See [desktop-app/README.md](./desktop-app/README.md).

## From source, one command

Requirements: Python 3.11+, Node.js 18+ and npm.

```bash
./launch.sh          # Linux / macOS
```

```
launch.bat           # Windows, Command Prompt
.\launch.ps1         # Windows, PowerShell
```

The launcher:

1. checks the prerequisites;
2. creates `backend/venv` and installs the Python packages;
3. installs the frontend packages;
4. starts the backend on port 8000 and the frontend on port 5173;
5. opens http://localhost:5173.

## From source, by hand

```bash
# Terminal 1: backend
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Terminal 2: frontend
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. The interactive API docs are at
http://localhost:8000/docs.

## First steps

1. In the **Lens Data Editor**, click **Samples** and pick a published
   lens (the Geiser triplet is a good start), or choose a **Preset**
   from the header.
2. Click **Resolve**. The analysis panel and the tabs below the editor
   now show this lens.
3. Look at the **Lens Layout**, **Ray Fan**, **MTF** and **PSF** tabs.
4. Mark radii as variables, add a constraint (for example the focal
   length) and click **Optimize**.
5. **Analyse with default tolerances** gives the tolerance budget. The
   **Report** tab saves everything as a PDF.

[USER_GUIDE.md](./USER_GUIDE.md) walks through the whole app.

## Troubleshooting

`./troubleshoot.sh` checks the setup.

- **Port in use:** stop whatever is using port 8000 or 5173.
- **Missing Python or Node.js:** install them from https://python.org and
  https://nodejs.org.
- **The first analysis is slow:** the compiled ray trace (Numba) compiles
  its kernels on first use and caches them. Later runs are fast.
