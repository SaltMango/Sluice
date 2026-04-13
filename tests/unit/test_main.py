from __future__ import annotations

import argparse
import asyncio
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


def test_main_completion_path(import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = import_engine("engine.main")

    class FakeController:
        def __init__(self, engine: object) -> None:
            self.engine = engine
            self.calls: list[str] = []

        async def run(self, torrent_file: str) -> SimpleNamespace:
            self.calls.append(torrent_file)
            return SimpleNamespace(status=SimpleNamespace(progress=100.0))

    fake_controller = FakeController(engine=object())
    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))
    monkeypatch.setattr(main_module, "TorrentEngine", object)
    monkeypatch.setattr(main_module, "Controller", lambda engine: fake_controller)

    assert main_module.main() == 0
    output = capsys.readouterr().out

    assert fake_controller.calls == ["movie.torrent"]
    assert "Torrent added. Press Ctrl+C to stop." in output
    assert "Download complete." in output
    assert "Torrent monitor stopped." not in output


def test_main_keyboard_interrupt_path(
    import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module = import_engine("engine.main")

    class FakeController:
        def __init__(self, engine: object) -> None:
            self.stopped = False

        async def run(self, _torrent_file: str) -> SimpleNamespace:
            return SimpleNamespace(status=SimpleNamespace(progress=100.0))

        def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))
    monkeypatch.setattr(main_module, "TorrentEngine", object)
    fake_controller = FakeController(engine=object())
    monkeypatch.setattr(main_module, "Controller", lambda engine: fake_controller)

    def raise_keyboard_interrupt(coroutine: object) -> object:
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(main_module.asyncio, "run", raise_keyboard_interrupt)

    assert main_module.main() == 0
    assert fake_controller.stopped is True
    assert "Stopping torrent monitor." in capsys.readouterr().out


def test_main_non_complete_path(import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = import_engine("engine.main")

    class FakeController:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        async def run(self, _torrent_file: str) -> SimpleNamespace:
            return SimpleNamespace(status=SimpleNamespace(progress=25.0))

    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))
    monkeypatch.setattr(main_module, "TorrentEngine", object)
    monkeypatch.setattr(main_module, "Controller", FakeController)

    assert main_module.main() == 0
    assert "Torrent monitor stopped." in capsys.readouterr().out


def test_module_entrypoint_runs_main(import_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_engine_modules()

    class FakeController:
        def __init__(self, engine: object) -> None:
            self.engine = engine

        async def run(self, _file_path: str) -> SimpleNamespace:
            return SimpleNamespace(status=SimpleNamespace(progress=100.0))

    stub_engine_module = ModuleType("engine.torrent")
    stub_engine_module.TorrentEngine = object
    stub_engine_module.TorrentStatus = SimpleNamespace
    monkeypatch.setitem(sys.modules, "engine.torrent", stub_engine_module)
    stub_controller_module = ModuleType("engine.controller")
    stub_controller_module.Controller = FakeController
    stub_controller_module.ControllerSnapshot = SimpleNamespace
    monkeypatch.setitem(sys.modules, "engine.controller", stub_controller_module)

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
