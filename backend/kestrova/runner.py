"""
Runs console scripts for the in-app console.

Each script runs in a fresh process (spawned, so a crash or an endless
loop cannot take the engine down) with a time limit. The namespace holds
``ks`` (the kestrova module), ``np`` (NumPy) and, when the editor has a
lens open, ``lens`` (a kestrova.Lens). Printed output is captured; if the
script leaves a Lens in ``lens``, its prescription is returned so the
editor can apply it.
"""

from __future__ import annotations

import inspect
import multiprocessing
import time
import traceback
from typing import Any, Optional

#: Captured output is cut to this many characters.
MAX_OUTPUT = 200_000


def _trim_traceback(text: str) -> str:
    """Drop the runner's own frames: keep from the script's first frame."""
    lines = text.splitlines()
    for k, line in enumerate(lines):
        if 'File "<console>"' in line:
            return "Traceback (most recent call last):\n" + "\n".join(lines[k:])
    return text


def _execute(code: str, lens: Optional[dict]) -> dict:
    import contextlib
    import io

    import numpy as np

    import kestrova as ks

    buf = io.StringIO()
    out: dict[str, Any] = {"output": "", "error": None, "lens": None}
    namespace: dict[str, Any] = {
        "ks": ks,
        "kestrova": ks,
        "np": np,
        "__name__": "__console__",
    }
    if lens is not None:
        namespace["lens"] = ks.from_dict(lens)
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(compile(code, "<console>", "exec"), namespace)
        result = namespace.get("lens")
        if isinstance(result, ks.Lens):
            out["lens"] = result.to_dict()
    except SystemExit:
        pass
    except BaseException:
        out["error"] = _trim_traceback(traceback.format_exc())
    text = buf.getvalue()
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + "\n... (output cut)"
    out["output"] = text
    return out


def _worker(code: str, lens: Optional[dict], conn) -> None:
    try:
        conn.send(_execute(code, lens))
    except BaseException:  # e.g. a result that cannot be pickled
        conn.send({"output": "", "error": traceback.format_exc(), "lens": None})
    finally:
        conn.close()


def run_script(code: str, lens: Optional[dict] = None, timeout: float = 120.0) -> dict:
    """
    Run a script in its own process.

    Returns:
        output: printed text; error: the traceback (None on success);
        lens: the resulting prescription (JSON form) or None;
        duration: seconds; timed_out: whether the limit stopped it.
    """
    ctx = multiprocessing.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_worker, args=(code, lens, send), daemon=True)
    start = time.monotonic()
    proc.start()
    send.close()
    deadline = start + timeout
    result: Optional[dict] = None
    try:
        while result is None:
            if receive.poll(0.05):
                result = receive.recv()
                result["timed_out"] = False
            elif not proc.is_alive():
                if receive.poll(0):
                    continue
                proc.join(1)
                result = {
                    "output": "",
                    "error": "The script process ended unexpectedly "
                    f"(exit code {proc.exitcode})",
                    "lens": None,
                    "timed_out": False,
                }
            elif time.monotonic() > deadline:
                result = {
                    "output": "",
                    "error": f"Stopped: the script ran longer than {timeout:g} s",
                    "lens": None,
                    "timed_out": True,
                }
    except EOFError:
        result = {
            "output": "",
            "error": f"The script process ended unexpectedly (exit code {proc.exitcode})",
            "lens": None,
            "timed_out": False,
        }
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(5)
        receive.close()
    result["duration"] = time.monotonic() - start
    return result


def _signature(fn) -> str:
    try:
        sig = inspect.signature(fn, eval_str=True)
    except Exception:
        sig = inspect.signature(fn)
    text = str(sig).replace("pathlib.", "").replace("optics.lens_data.", "")
    return text.replace("kestrova.", "").replace("(self, ", "(").replace("(self)", "()")


def _first_paragraph(doc: Optional[str]) -> str:
    text = inspect.cleandoc(doc or "")
    return text.split("\n\n")[0].replace("\n", " ")


def api_reference() -> list[dict]:
    """The scripting API for the console's help: name, signature, summary."""
    import kestrova as ks

    out = []
    for name in ("sample", "samples", "open_lens", "from_dict"):
        fn = getattr(ks, name)
        out.append(
            {
                "name": f"ks.{name}",
                "signature": _signature(fn),
                "doc": _first_paragraph(fn.__doc__),
            }
        )
    for name, member in inspect.getmembers(ks.Lens):
        if name.startswith("_"):
            continue
        if isinstance(member, property):
            out.append(
                {
                    "name": f"lens.{name}",
                    "signature": "",
                    "doc": _first_paragraph(member.__doc__),
                }
            )
        elif callable(member):
            out.append(
                {
                    "name": f"lens.{name}",
                    "signature": _signature(member),
                    "doc": _first_paragraph(member.__doc__),
                }
            )
    return out
