from __future__ import annotations

import argparse
import asyncio

try:
    from engine.controller import Controller
    from engine.torrent import TorrentEngine
except ModuleNotFoundError:  # pragma: no cover - convenience for direct script execution
    from controller import Controller
    from torrent import TorrentEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal torrent downloader.")
    parser.add_argument("torrent_file", help="Path to a .torrent file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    controller = Controller(engine=TorrentEngine())

    try:
        print("Torrent added. Press Ctrl+C to stop.")
        snapshot = asyncio.run(controller.run(args.torrent_file))
        print()
        if snapshot is not None and snapshot.status.progress >= 100.0:
            print("Download complete.")
        else:
            print("Torrent monitor stopped.")
        return 0
    except KeyboardInterrupt:
        controller.stop()
        print("\nStopping torrent monitor.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
