"""
Tests for what the desktop app relies on: where user data is kept, the web
interface served by the backend, and the kestrova_server entry point (free
port, the KESTROVA_PORT line, and exiting when its standard input closes).
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import persistence
from api import main

BACKEND = Path(__file__).resolve().parents[1]


class TestDataDir:

    def test_environment_variable_wins(self, tmp_path, monkeypatch):
        target = tmp_path / "data"
        monkeypatch.setenv("KESTROVA_DATA_DIR", str(target))
        assert persistence.data_dir() == target and target.is_dir()

    def test_source_tree_by_default(self, monkeypatch):
        monkeypatch.delenv("KESTROVA_DATA_DIR", raising=False)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert persistence.data_dir() == BACKEND

    @pytest.mark.parametrize(
        "platform,parts",
        [("win32", ("AppData", "Kestrova")),
         ("darwin", ("Library", "Application Support", "Kestrova")),
         ("linux", (".local", "share", "kestrova"))],
    )
    def test_frozen_build_uses_the_os_user_folder(self, tmp_path, monkeypatch, platform,
                                                  parts):
        monkeypatch.delenv("KESTROVA_DATA_DIR", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
        assert persistence.data_dir() == tmp_path.joinpath(*parts)


class TestWebInterface:

    def test_directory_from_environment(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html>Kestrova</html>")
        monkeypatch.setenv("KESTROVA_FRONTEND_DIR", str(tmp_path))
        assert main._frontend_dir() == tmp_path
        monkeypatch.setenv("KESTROVA_FRONTEND_DIR", str(tmp_path / "missing"))
        assert main._frontend_dir() != tmp_path / "missing"

    def test_root_serves_the_interface_when_built(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html>Kestrova</html>")
        monkeypatch.setattr(main, "FRONTEND_DIR", tmp_path)
        r = TestClient(main.app).get("/")
        assert r.status_code == 200 and "Kestrova" in r.text
        assert r.headers["content-type"].startswith("text/html")

    def test_root_describes_the_api_otherwise(self, monkeypatch):
        monkeypatch.setattr(main, "FRONTEND_DIR", None)
        client = TestClient(main.app)
        assert client.get("/").json() == client.get("/api").json()
        assert "endpoints" in client.get("/api").json()


def test_watching_a_finished_process_returns_at_once():
    import kestrova_server

    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    start = time.time()
    kestrova_server.wait_for_exit(done.pid)
    assert time.time() - start < 5


def test_server_reports_its_port_and_exits_with_the_app():
    # a stand-in for the desktop app: the server watches its process id
    app = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)"])
    proc = subprocess.Popen(
        [sys.executable, str(BACKEND / "kestrova_server.py"), "--port", "0",
         "--parent-pid", str(app.pid)],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        line, start = "", time.time()
        while "KESTROVA_PORT=" not in line and time.time() - start < 300:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
        assert "KESTROVA_PORT=" in line, "the server did not report its port"
        port = int(line.strip().split("=")[1])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=30) as r:
            assert json.load(r)["status"] == "healthy"
        app.kill()  # the app ends, however it ends
        app.wait()
        assert proc.wait(timeout=30) == 0
    finally:
        for p in (proc, app):
            if p.poll() is None:
                p.kill()
