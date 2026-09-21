"""File storage abstraction: local filesystem now; the same interface can back an object store (S3-compatible)."""
from __future__ import annotations

import os
import shutil
from typing import BinaryIO, Protocol

from .config import settings


class Storage(Protocol):
    def put(self, key: str, fh: BinaryIO) -> str: ...
    def path(self, key: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def open(self, key: str) -> BinaryIO: ...
    def list(self, prefix: str) -> list[str]: ...
    def delete_prefix(self, prefix: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _p(self, key: str) -> str:
        p = os.path.abspath(os.path.join(self.root, key))
        # Ett prefix utan avskiljare släpper igenom grannen: med roten /data/storage duger /data/storage2/x som
        # "innanför". Så antingen roten själv, eller något under den med avskiljaren emellan.
        if p != self.root and not p.startswith(self.root + os.sep):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, fh: BinaryIO) -> str:
        p = self._p(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as out:
            shutil.copyfileobj(fh, out)
        return key

    def path(self, key: str) -> str:
        return self._p(key)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._p(key))

    def open(self, key: str) -> BinaryIO:
        return open(self._p(key), "rb")

    def list(self, prefix: str) -> list[str]:
        base = self._p(prefix)
        if not os.path.isdir(base):
            return []
        out = []
        for dirpath, _, files in os.walk(base):
            for f in files:
                out.append(os.path.relpath(os.path.join(dirpath, f), self.root))
        return sorted(out)

    def delete_prefix(self, prefix: str) -> None:
        base = self._p(prefix)
        if os.path.isdir(base):
            shutil.rmtree(base)


storage: Storage = LocalStorage(settings.storage_root)
