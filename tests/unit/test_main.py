from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tests.conftest import REPO_ROOT, clear_engine_modules


def test_parse_args_and_format_speed(import_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    main_module = import_engine("engine.main")
    monkeypatch.setattr(sys, "argv", ["engine.main", "movie.torrent"])

    args = main_module.parse_args()

    assert args == argparse.Namespace(torrent_file="movie.torrent")
    assert main_module.format_speed(512) == "512.0 B/s"
    assert main_module.format_speed(2048) == "2.0 KiB/s"
    assert main_module.format_speed(5 * 1024 * 1024) == "5.0 MiB/s"
    assert main_module.format_speed(3 * 1024 * 1024 * 1024) == "3.0 GiB/s"


def test_main_completion_path(import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = import_engine("engine.main")

    class FakeEngine:
        def __init__(self) -> None:
            self.started = False
            self.torrent_path: str | None = None
            self.status_calls = 0

        def start_session(self) -> None:
            self.started = True

        def add_torrent(self, file_path: str) -> None:
            self.torrent_path = file_path

        def get_status(self) -> SimpleNamespace:
            self.status_calls += 1
            if self.status_calls == 1:
                return SimpleNamespace(progress=40.0, download_rate=1024, peers=2)
            return SimpleNamespace(progress=100.0, download_rate=2048, peers=4)

    fake_engine = FakeEngine()
    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))
    monkeypatch.setattr(main_module, "TorrentEngine", lambda: fake_engine)
    monkeypatch.setattr(main_module.time, "sleep", lambda _seconds: None)

    assert main_module.main() == 0
    output = capsys.readouterr().out

    assert fake_engine.started is True
    assert fake_engine.torrent_path == "movie.torrent"
    assert "Torrent added. Press Ctrl+C to stop." in output
    assert "Progress: 100.00%" in output
    assert "Download complete." in output


def test_main_keyboard_interrupt_path(
    import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module = import_engine("engine.main")

    class FakeEngine:
        def start_session(self) -> None:
            pass

        def add_torrent(self, _file_path: str) -> None:
            pass

        def get_status(self) -> SimpleNamespace:
            raise KeyboardInterrupt

    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))
    monkeypatch.setattr(main_module, "TorrentEngine", FakeEngine)

    assert main_module.main() == 0
    assert "Stopping torrent monitor." in capsys.readouterr().out


def test_module_entrypoint_runs_main(import_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_engine_modules()

    class FakeEngine:
        def start_session(self) -> None:
            pass

        def add_torrent(self, _file_path: str) -> None:
            pass

        def get_status(self) -> SimpleNamespace:
            return SimpleNamespace(progress=100.0, download_rate=0, peers=0)

    stub_engine_module = ModuleType("engine.torrent")
    stub_engine_module.TorrentEngine = FakeEngine
    stub_engine_module.TorrentStatus = SimpleNamespace
    monkeypatch.setitem(sys.modules, "engine.torrent", stub_engine_module)

    monkeypatch.setattr(sys, "argv", ["engine.main", "movie.torrent"])
    monkeypatch.setattr(
        "argparse.ArgumentParser.parse_args",
        lambda self: argparse.Namespace(torrent_file="movie.torrent"),
    )

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("engine.main", run_name="__main__", alter_sys=True)

    assert exc_info.value.code == 0


def test_script_entrypoint_falls_back_to_local_import(libtorrent_stub, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_engine_modules()
    engine_dir = REPO_ROOT / "engine"
    filtered_path = [path for path in sys.path if Path(path or ".").resolve() != REPO_ROOT]
    monkeypatch.setattr(sys, "path", [str(engine_dir), *filtered_path])
    monkeypatch.setattr(sys, "argv", [str(engine_dir / "main.py"), "--help"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(engine_dir / "main.py"), run_name="__main__")

    assert exc_info.value.code == 0
