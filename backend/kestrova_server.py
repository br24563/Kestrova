"""
Kestrova backend server: the entry point of the desktop app's bundled
(frozen) backend, also usable from source.

    python kestrova_server.py [--host 127.0.0.1] [--port 0] [--parent-pid PID]

With ``--port 0`` a free port is chosen. Once the server is listening it
prints ``KESTROVA_PORT=<port>`` on its own line (the desktop app waits for
it). With ``--parent-pid`` it exits when that process ends, so it never
outlives the desktop app, however the app ends.
"""

import argparse
import multiprocessing
import os
import socket
import sys
import threading
import time


def free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def wait_for_exit(pid: int) -> None:
    """Return when process ``pid`` has ended (or cannot be watched)."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE, INFINITE = 0x00100000, 0xFFFFFFFF
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return  # already gone
        kernel32.WaitForSingleObject(handle, INFINITE)
        kernel32.CloseHandle(handle)
        return
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            pass  # exists, owned by someone else
        time.sleep(1.0)


def _exit_with(pid: int) -> None:
    wait_for_exit(pid)
    os._exit(0)


def numba_cache_dir() -> "str | None":
    """Where a frozen build caches the compiled ray-trace kernels across
    launches: with the user's data (the install folder may be read-only).
    None from source (Numba caches beside the module) or when set already."""
    if not getattr(sys, "frozen", False) or os.environ.get("NUMBA_CACHE_DIR"):
        return None
    base = os.environ.get("KESTROVA_DATA_DIR") or os.path.join(
        os.path.expanduser("~"), ".kestrova"
    )
    return os.path.join(base, "numba-cache")


def _warm_up() -> None:
    """Load the compiled ray-trace kernels while the window opens."""
    try:
        from optics import _fasttrace

        _fasttrace.warm_up()
    except Exception as e:  # never fatal: the first trace compiles instead
        print(f"warm-up skipped: {e}", flush=True)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Kestrova backend server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 = any free port")
    parser.add_argument(
        "--parent-pid", type=int, default=None, help="exit when this process ends"
    )
    args = parser.parse_args(argv)
    if args.parent_pid:
        threading.Thread(
            target=_exit_with, args=(args.parent_pid,), daemon=True
        ).start()
    port = args.port or free_port(args.host)

    cache = numba_cache_dir()
    if cache:
        os.environ["NUMBA_CACHE_DIR"] = cache

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import uvicorn

    from api.main import app

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            print(f"KESTROVA_PORT={port}", flush=True)
            threading.Thread(target=_warm_up, daemon=True).start()

    Server(uvicorn.Config(app, host=args.host, port=port, log_level="warning")).run()


if __name__ == "__main__":
    # needed for the spawned ray-trace worker processes of a frozen build
    multiprocessing.freeze_support()
    main()
