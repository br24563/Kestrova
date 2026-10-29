# PyInstaller spec for the desktop app's backend (one folder, per OS).
#   cd backend && pyinstaller kestrova-server.spec
# Needs the web interface built first (frontend/dist).
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

here = Path(SPECPATH)
frontend = here.parent / "frontend" / "dist"
if not (frontend / "index.html").is_file():
    raise SystemExit("Build the web interface first: cd frontend && npm run build")

datas = [(str(here / "optics" / "data"), "optics/data"), (str(frontend), "frontend")]
binaries = []
hiddenimports = collect_submodules("uvicorn") + collect_submodules("api") + collect_submodules("ai")
# Numba is optional (not installed on Intel Macs): bundle it when present
for pkg in ("numba", "llvmlite"):
    if importlib.util.find_spec(pkg) is None:
        continue
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(here / "kestrova_server.py")],
    pathex=[str(here)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="kestrova-server",
    console=True,
)
COLLECT(exe, a.binaries, a.datas, name="kestrova-server")
