"""Tiny generic plugin registry.

Used by the connector, engine, and tool-adapter factories so external code can
register custom implementations without editing an if/elif chain. Each registry
maps a string key to a zero-argument factory callable that produces an instance.
This indirection keeps optional heavy dependencies (e.g. pyspark, snowflake,
pydeequ) lazy: the callable performs its imports only when invoked.
"""

from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
Factory = Callable[[], T]


class PluginRegistry:
    def __init__(self, kind: str):
        self._kind = kind
        self._factories: dict[str, Factory] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        name: str,
        factory: Factory,
        aliases: Iterable[str] | None = None,
    ) -> None:
        key = name.lower()
        self._factories[key] = factory
        if aliases:
            for alias in aliases:
                self._aliases[alias.lower()] = key

    def create(self, name: str):
        key = (name or "").lower()
        key = self._aliases.get(key, key)
        if key not in self._factories:
            raise ValueError(
                f"Unsupported {self._kind}: {name!r}. "
                f"Registered: {sorted(self._factories.keys())}"
            )
        return self._factories[key]()

    def names(self) -> list:
        return sorted(self._factories.keys())

    def __contains__(self, name: str) -> bool:
        key = (name or "").lower()
        return self._aliases.get(key, key) in self._factories
