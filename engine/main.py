from __future__ import annotations

import argparse
import time

try:
    from engine.torrent import TorrentEngine
except ModuleNotFoundError:  # pragma: no cover - convenience for direct script execution
    from torrent import TorrentEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal torrent downloader.")
    parser.add_argument("torrent_file", help="Path to a .torrent file")
    return parser.parse_args()


def format_speed(bytes_per_second: int) -> str:
    units = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
    value = float(bytes_per_second)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{value:.1f} GiB/s"


def main() -> int:
    args = parse_args()

    engine = TorrentEngine()
    engine.start_session()
    engine.add_torrent(args.torrent_file)

    print("Torrent added. Press Ctrl+C to stop.")

    try:
        while True:
            status = engine.get_status()
            line = (
                f"\rProgress: {status.progress:6.2f}% | "
                f"Download: {format_speed(status.download_rate):>12} | "
                f"Peers: {status.peers:3d}"
            )
            print(line, end="", flush=True)

            if status.progress >= 100.0:
                print()
                print("Download complete.")
                return 0

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping torrent monitor.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
