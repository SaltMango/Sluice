from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Callable, Iterator

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_DIST_PACKAGES = Path("/usr/lib/python3/dist-packages")
ENGINE_MODULES = ("engine", "engine.main", "engine.peers", "engine.torrent", "torrent")
ImportEngine = Callable[[str], types.ModuleType]


def clear_engine_modules() -> None:
    for module_name in ENGINE_MODULES:
        sys.modules.pop(module_name, None)


def make_libtorrent_stub() -> types.ModuleType:
    module = types.ModuleType("libtorrent")

    def _unconfigured(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("libtorrent stub member was used without test configuration")

    setattr(module, "session", _unconfigured)
    setattr(module, "torrent_info", _unconfigured)
    setattr(module, "peer_info", types.SimpleNamespace(remote_choked=8))
    return module


@pytest.fixture
def libtorrent_stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[types.ModuleType]:
    clear_engine_modules()
    stub = make_libtorrent_stub()
    monkeypatch.setitem(sys.modules, "libtorrent", stub)
    yield stub
    clear_engine_modules()


@pytest.fixture
def import_engine(libtorrent_stub: types.ModuleType) -> Iterator[ImportEngine]:
    def _import(module_name: str) -> types.ModuleType:
        return importlib.import_module(module_name)

    yield _import


@pytest.fixture
def enable_real_libtorrent(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    clear_engine_modules()
    monkeypatch.delitem(sys.modules, "libtorrent", raising=False)
    sys.path.append(str(SYSTEM_DIST_PACKAGES))
    try:
        yield
    finally:
        while str(SYSTEM_DIST_PACKAGES) in sys.path:
            sys.path.remove(str(SYSTEM_DIST_PACKAGES))
        clear_engine_modules()
