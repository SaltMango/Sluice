from __future__ import annotations

import argparse
import asyncio
import sys
from importlib import import_module
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from engine.controller import ControllerSnapshot, StatsPrinter


def _load_runtime_dependencies() -> tuple[type[Any], type[Any]]:
    try:
        controller_module = import_module("engine.controller")
        torrent_module = import_module("engine.torrent")
    except ModuleNotFoundError:  # pragma: no cover - convenience for direct script execution
        controller_module = import_module("controller")
        torrent_module = import_module("torrent")

    controller_class = getattr(controller_module, "Controller")
    torrent_engine_class = getattr(torrent_module, "TorrentEngine")
    return controller_class, torrent_engine_class


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal torrent downloader.")
    parser.add_argument("torrent_file", help="Path to a .torrent file")
    return parser.parse_args()


def format_speed(bytes_per_second: int) -> str:
    units = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
    value = float(bytes_per_second)

    for unit in units[:-1]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{value:.1f} {units[-1]}"


def format_mode(snapshot: ControllerSnapshot) -> str:
    if snapshot.bandwidth is not None and snapshot.bandwidth.aggressive_mode:
        return "aggressive"
    return "normal"


def render_snapshot(snapshot: ControllerSnapshot) -> str:
    return (
        f"\rProgress: {snapshot.status.progress:6.2f}% | "
        f"Speed: {format_speed(snapshot.status.download_rate):>12} | "
        f"Peers: {snapshot.status.peers:3d} | "
        f"Mode: {format_mode(snapshot)}"
    )


def build_cli_printer(output: TextIO = sys.stdout) -> StatsPrinter:
    def _print_snapshot(snapshot: ControllerSnapshot) -> None:
        print(render_snapshot(snapshot), end="", flush=True, file=output)

    return _print_snapshot


async def run_cli(torrent_file: str, output: TextIO = sys.stdout) -> ControllerSnapshot | None:
    controller_class, torrent_engine_class = _load_runtime_dependencies()
    controller = controller_class(
        engine=torrent_engine_class(),
        stats_printer=build_cli_printer(output),
    )
    return await controller.run(torrent_file)


def main() -> int:
    args = parse_args()

    try:
        print("Starting torrent controller. Press Ctrl+C to stop.")
        snapshot = asyncio.run(run_cli(args.torrent_file))
        print(file=sys.stdout)
        if snapshot is not None and snapshot.status.progress >= 100.0:
            print("Download complete.")
        else:
            print("Torrent monitor stopped.")
        return 0
    except KeyboardInterrupt:
        print("\nStopping torrent monitor.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
