import argparse
import asyncio
import sys

from engine.controller import Controller
from engine.config import EngineConfig
from engine.logger import get_logger

logger = get_logger("engine.main")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Production Torrent Engine.")
    parser.add_argument("torrent_file", help="Path to a .torrent file")
    return parser.parse_args()

async def run_torrent(torrent_file: str) -> None:
    config = EngineConfig()
    controller = Controller(config)

    logger.info("Starting torrent service", extra={"file": torrent_file})
    try:
        await controller.run(torrent_file)
    finally:
        state = controller.get_state()
        if state and state.progress >= 100.0:
            logger.info("Download finished gracefully")
        else:
            logger.info("Torrent monitor stopped before completion")

def main() -> int:
    args = parse_args()

    try:
        asyncio.run(run_torrent(args.torrent_file))
        return 0
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt detected. Shutting down proactively.")
        return 0
    except Exception as e:
        logger.critical("Fatal exception encountered", extra={"error": str(e)})
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
