"""Pluggable history backend for drift detection.

The drift detector compares the current run with the previous one. The
sequence of historical runs is stored somewhere durable -- by default in a
local JSON file, but the kit can also persist history in any place that can
load + save a JSON-shaped dict (S3, GCS, Postgres JSONB, an HTTP API, an
in-memory dict for tests).

This module defines the contract:

```python
class HistoryBackend(Protocol):
    def load(self) -> dict: ...
    def save(self, history: dict) -> None: ...
    def describe(self) -> str: ...
```

and ships two implementations:

* ``FileHistoryBackend`` — the original local-file behavior, including
  archiving corrupt or malformed history files so a single bad run can't
  permanently poison drift detection.
* ``InMemoryHistoryBackend`` — for unit tests; no I/O.

External code can register a custom backend factory via
``register_history_backend(name, factory)`` and then pass
``history_backend: name`` in the drift config to swap in cloud storage
without editing the kit.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from fidu.core.registry import PluginRegistry


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_history() -> dict:
    return {"runs": []}


class HistoryBackend(ABC):
    """Persistent store for the per-project drift history.

    Implementations only need to handle two ops: load the current history
    blob and overwrite it. The blob shape is ``{"runs": [...], "warnings":
    [...] (optional)}``. The drift detector never mutates the loaded blob
    in place -- it always builds a new one and calls ``save``.
    """

    @abstractmethod
    def load(self) -> dict:
        """Return the current history. Must return ``{"runs": []}`` when empty."""
        raise NotImplementedError

    @abstractmethod
    def save(self, history: dict) -> None:
        """Persist the history blob, overwriting any prior state."""
        raise NotImplementedError

    def describe(self) -> str:
        """Human-readable description for logs (e.g. file path, bucket key)."""
        return type(self).__name__


class FileHistoryBackend(HistoryBackend):
    """Local-filesystem backend.

    Loads JSON from ``path``. If the file is missing, returns an empty
    history. If it exists but is corrupt or malformed, archives the bad
    file (timestamped) and returns an empty history with a warning, so the
    next run can still execute drift detection cleanly.
    """

    def __init__(self, path: str):
        self.path = path

    def describe(self) -> str:
        return f"file://{os.path.abspath(self.path)}"

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return _empty_history()
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return self._archive_and_reset(reason="corrupt")
        if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
            return self._archive_and_reset(reason="malformed")
        return data

    def save(self, history: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, default=str)

    def _archive_and_reset(self, reason: str) -> dict:
        suffix = _utcnow_iso().replace(":", "-")
        archived = f"{self.path}.{reason}-{suffix}"
        with contextlib.suppress(OSError):
            shutil.move(self.path, archived)
        return {
            "runs": [],
            "warnings": [
                f"Previous history was {reason} and archived to {archived}"
            ],
        }


class InMemoryHistoryBackend(HistoryBackend):
    """Test-friendly backend; persists nothing across processes."""

    def __init__(self, initial: dict | None = None):
        self._history = initial if initial is not None else _empty_history()

    def describe(self) -> str:
        return "memory://"

    def load(self) -> dict:
        # Return a deep-copy-ish view so callers that mutate don't bleed
        # into the next load. JSON round-trip is the cheapest deep copy
        # and matches what a real backend would return.
        return json.loads(json.dumps(self._history, default=str))

    def save(self, history: dict) -> None:
        self._history = json.loads(json.dumps(history, default=str))


# --- registry ---------------------------------------------------------------

history_backend_registry: PluginRegistry = PluginRegistry("history backend")


def _register_builtins() -> None:
    history_backend_registry.register("file", lambda: None)  # type: ignore[arg-type]
    history_backend_registry.register("memory", lambda: InMemoryHistoryBackend())


_register_builtins()


def register_history_backend(name, factory, aliases=None):
    """Public hook for downstream code to register a custom backend factory.

    The factory should accept a ``config: dict`` and return a
    ``HistoryBackend`` instance. ``config`` is the ``drift.history_backend``
    block from the kit's config YAML, minus the ``type`` key.
    """
    history_backend_registry.register(name, factory, aliases=aliases)


def resolve_history_backend(
    history_path: str | None,
    drift_config: dict | None = None,
) -> HistoryBackend:
    """Resolve a backend from the ``drift`` config block.

    Precedence:

    1. If ``drift_config`` includes ``history_backend`` as an already-built
       ``HistoryBackend`` instance, use it directly. (Library callers can
       inject a custom backend without going through the registry.)
    2. Else, if ``drift_config['history_backend']`` is a dict with a
       ``type`` key, look that name up in the registry.
    3. Otherwise default to ``FileHistoryBackend(history_path)``.

    The default keeps the original config surface working: just set
    ``drift.history_path`` and you get a file backend.
    """
    drift_config = drift_config or {}
    spec = drift_config.get("history_backend")
    if isinstance(spec, HistoryBackend):
        return spec
    if isinstance(spec, dict):
        backend_type = spec.get("type", "file")
        if backend_type == "file":
            path = spec.get("path", history_path)
            if not path:
                raise ValueError(
                    "history_backend.type='file' requires a 'path' or "
                    "fidu.drift.history_path in the drift config"
                )
            return FileHistoryBackend(path)
        if backend_type == "memory":
            return InMemoryHistoryBackend(spec.get("initial"))
        # registry-resolved custom backend
        if backend_type not in history_backend_registry:
            raise ValueError(
                f"Unknown history backend type: {backend_type!r}. "
                f"Registered: {history_backend_registry.names()}"
            )
        factory = history_backend_registry._factories[backend_type]  # noqa: SLF001
        config = {k: v for k, v in spec.items() if k != "type"}
        return factory(config)
    if not history_path:
        raise ValueError(
            "drift detection requires either fidu.drift.history_path or "
            "fidu.drift.history_backend in the drift config"
        )
    return FileHistoryBackend(history_path)


__all__ = [
    "FileHistoryBackend",
    "HistoryBackend",
    "InMemoryHistoryBackend",
    "history_backend_registry",
    "register_history_backend",
    "resolve_history_backend",
]
