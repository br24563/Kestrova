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
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("api")
    + collect_submodules("ai")
    + collect_submodules("kestrova")
    + collect_submodules("optics")
)
# SciPy's vendored array-API layer is imported dynamically (its location
# moved in SciPy 1.18); collect it wherever this SciPy keeps it.
for pkg in ("scipy._external.array_api_compat", "scipy._lib.array_api_compat"):
    try:
        found = importlib.util.find_spec(pkg) is not None
    except ModuleNotFoundError:
        found = False
    if found:
        hiddenimports += collect_submodules(pkg)

# Parts of packages the engine never imports (GPU, test suites, type
# checkers, docs); they are most of what a naive bundle carries.
_UNUSED = (".cuda", ".tests", ".testing._private.extbuild", "._testing")


def _used(name: str) -> bool:
    return not any(part in name for part in _UNUSED)


# Numba is optional (not installed on Intel Macs): bundle it when present
for pkg in ("numba", "llvmlite"):
    if importlib.util.find_spec(pkg) is None:
        continue
    d, b, h = collect_all(pkg, filter_submodules=_used)
    datas += [x for x in d if _used(x[1].replace("/", ".").replace("\\", "."))]
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(here / "kestrova_server.py")],
    pathex=[str(here)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter",
        "matplotlib",
        "pytest",
        "IPython",
        "mypy",
        "mypyc",
        "sympy",
        "setuptools",
        "pip",
        "PIL",
        "numba.cuda",
        "scipy.io.matlab.tests",
    ],
    # the compiled ray trace's kernels are cached on disk keyed on their
    # source file, so that module ships as source (see optics/_fasttrace.py)
    module_collection_mode={"optics._fasttrace": "py"},
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
