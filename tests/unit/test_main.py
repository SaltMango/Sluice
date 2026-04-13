from __future__ import annotations

import argparse
import asyncio
import runpy
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Coroutine
from types import ModuleType, SimpleNamespace

import pytest

from tests.conftest import REPO_ROOT, clear_engine_modules


def test_parse_args_and_format_helpers(import_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    main_module = import_engine("engine.main")
    monkeypatch.setattr(sys, "argv", ["engine.main", "movie.torrent"])

    args = main_module.parse_args()

    assert args == argparse.Namespace(torrent_file="movie.torrent")
    assert main_module.format_speed(512) == "512.0 B/s"
    assert main_module.format_speed(2048) == "2.0 KiB/s"
    assert main_module.format_speed(3 * 1024 * 1024 * 1024) == "3.0 GiB/s"
    normal_snapshot = SimpleNamespace(
        status=SimpleNamespace(progress=42.0, download_rate=2048, peers=3),
        bandwidth=None,
    )
    aggressive_snapshot = SimpleNamespace(
        status=SimpleNamespace(progress=42.0, download_rate=2048, peers=3),
        bandwidth=SimpleNamespace(aggressive_mode=True),
    )
    assert main_module.format_mode(normal_snapshot) == "normal"
    assert main_module.format_mode(aggressive_snapshot) == "aggressive"
    assert "Progress:  42.00%" in main_module.render_snapshot(normal_snapshot)
    assert "Speed:    2.0 KiB/s" in main_module.render_snapshot(normal_snapshot)
    assert "Mode: normal" in main_module.render_snapshot(normal_snapshot)


def test_build_cli_printer(import_engine) -> None:
    main_module = import_engine("engine.main")
    buffer = StringIO()
    printer = main_module.build_cli_printer(buffer)
    snapshot = SimpleNamespace(
        status=SimpleNamespace(progress=12.5, download_rate=4096, peers=2),
        bandwidth=SimpleNamespace(aggressive_mode=True),
    )

    printer(snapshot)

    output = buffer.getvalue()
    assert "Progress:  12.50%" in output
    assert "Speed:    4.0 KiB/s" in output
    assert "Peers:   2" in output
    assert "Mode: aggressive" in output


def test_run_cli_uses_controller_with_cli_printer(import_engine) -> None:
    main_module = import_engine("engine.main")
    buffer = StringIO()
    created: dict[str, object] = {}

    class FakeController:
        def __init__(
            self, engine: object, stats_printer: Callable[[Any], None]
        ) -> None:
            self.engine = engine
            self.stats_printer = stats_printer
            self.calls: list[str] = []

        async def run(self, torrent_file: str) -> SimpleNamespace:
            self.calls.append(torrent_file)
            self.stats_printer(
                SimpleNamespace(
                    status=SimpleNamespace(progress=50.0, download_rate=1024, peers=1),
                    bandwidth=SimpleNamespace(aggressive_mode=False),
                )
            )
            return SimpleNamespace(status=SimpleNamespace(progress=100.0))

    def build_fake_controller(
        engine: object, stats_printer: Callable[[Any], None]
    ) -> FakeController:
        controller = FakeController(engine=engine, stats_printer=stats_printer)
        created["controller"] = controller
        return controller

    main_module._load_runtime_dependencies = lambda: (build_fake_controller, object)

    snapshot = asyncio.run(main_module.run_cli("movie.torrent", output=buffer))

    assert snapshot is not None
    controller = created["controller"]
    assert isinstance(controller, FakeController)
    assert controller.calls == ["movie.torrent"]
    assert "Mode: normal" in buffer.getvalue()


def test_main_completion_path(import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = import_engine("engine.main")

    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))
    monkeypatch.setattr(
        main_module,
        "run_cli",
        lambda torrent_file: asyncio.sleep(0, result=SimpleNamespace(status=SimpleNamespace(progress=100.0))),
    )

    assert main_module.main() == 0
    output = capsys.readouterr().out

    assert "Starting torrent controller. Press Ctrl+C to stop." in output
    assert "Download complete." in output
    assert "Torrent monitor stopped." not in output


def test_main_keyboard_interrupt_path(
    import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module = import_engine("engine.main")

    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))

    def raise_keyboard_interrupt(
        coroutine: Coroutine[Any, Any, object]
    ) -> object:
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(main_module.asyncio, "run", raise_keyboard_interrupt)

    assert main_module.main() == 0
    assert "Stopping torrent monitor." in capsys.readouterr().out


def test_main_non_complete_path(import_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = import_engine("engine.main")

    monkeypatch.setattr(main_module, "parse_args", lambda: argparse.Namespace(torrent_file="movie.torrent"))
    monkeypatch.setattr(
        main_module,
        "run_cli",
        lambda _torrent_file: asyncio.sleep(0, result=SimpleNamespace(status=SimpleNamespace(progress=25.0))),
    )

    assert main_module.main() == 0
    assert "Torrent monitor stopped." in capsys.readouterr().out


def test_module_entrypoint_runs_main(import_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_engine_modules()

    class FakeController:
        def __init__(
            self, engine: object, stats_printer: Callable[[Any], None]
        ) -> None:
            self.engine = engine
            self.stats_printer = stats_printer

        async def run(self, _file_path: str) -> SimpleNamespace:
            return SimpleNamespace(status=SimpleNamespace(progress=100.0))

    stub_engine_module = ModuleType("engine.torrent")
    setattr(stub_engine_module, "TorrentEngine", object)
    setattr(stub_engine_module, "TorrentStatus", SimpleNamespace)
    monkeypatch.setitem(sys.modules, "engine.torrent", stub_engine_module)
    stub_controller_module = ModuleType("engine.controller")
    setattr(stub_controller_module, "Controller", FakeController)
    setattr(stub_controller_module, "ControllerSnapshot", SimpleNamespace)
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
