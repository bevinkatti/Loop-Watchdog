"""Storage abstraction for Loop Watchdog persistence.

The core engine depends only on the ``SessionStore`` interface. The default
``JsonSessionStore`` implementation preserves the existing file-based JSON
persistence. Alternative backends (for example SQLite in a future task) can
implement the same interface without touching the core engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .models import PersistedStore


class SessionStore(ABC):
    """Abstract persistence backend for watchdog session state."""

    @abstractmethod
    def load(self) -> PersistedStore:
        """Load the persisted store.

        Returns an empty store when no state exists or the state cannot be read.
        """

    @abstractmethod
    def save(self, store: PersistedStore) -> None:
        """Persist the store."""


class JsonSessionStore(SessionStore):
    """File-based JSON persistence backend (the existing behavior)."""

    def __init__(self, persistence_path: Path | str) -> None:
        self._persistence_path = Path(persistence_path)

    def load(self) -> PersistedStore:
        if not self._persistence_path.exists():
            return PersistedStore()
        try:
            return PersistedStore.model_validate_json(
                self._persistence_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return PersistedStore()

    def save(self, store: PersistedStore) -> None:
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        target = self._persistence_path
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(store.model_dump_json(indent=2), encoding="utf-8")
        temp.replace(target)