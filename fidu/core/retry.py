"""Retry helper for transient connector failures.

Used by ``DQExecutor`` to wrap connector calls (``load_data``,
``execute_scalar_query``) so a transient network/auth blip doesn't tank a
whole DQ run. Opt-in per-source via the ``retry:`` block in the rule file:

.. code-block:: yaml

    source:
      type: snowflake
      retry:
        attempts: 3          # total attempts including the first call
        base_delay_ms: 200   # initial backoff
        max_delay_ms: 5000   # cap (otherwise base * 2^N grows fast)
        jitter: true         # uniform jitter in [0.5, 1.5] * delay
        retryable: ["OSError", "ConnectionError", "TimeoutError"]

Defaults to **no retries** (``attempts=1``) so bugs in tests don't get masked
by silent retries. Callers that don't pass a retry block see one call, one
exception, like before.

The helper itself is dependency-free; it does not import the kit's logger so
it can be reused outside the executor without dragging logging config along.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    OSError,
    ConnectionError,
    TimeoutError,
)


def _resolve_retryable(names: list[str] | None) -> tuple[type[BaseException], ...]:
    """Resolve a list of exception class names from YAML to concrete types.

    Unknown names are silently ignored -- the goal is to be permissive for
    deployments where, for example, ``snowflake.connector.errors.OperationalError``
    isn't importable in the parsing context. ``OSError`` is always included as
    a safe default.
    """
    if not names:
        return DEFAULT_RETRYABLE
    resolved: list[type[BaseException]] = [OSError]
    for name in names:
        cls = _BUILTIN_EXC_INDEX.get(name)
        if cls is not None and cls not in resolved:
            resolved.append(cls)
    return tuple(resolved)


_BUILTIN_EXC_INDEX: dict[str, type[BaseException]] = {
    "OSError": OSError,
    "IOError": OSError,
    "ConnectionError": ConnectionError,
    "ConnectionResetError": ConnectionResetError,
    "ConnectionRefusedError": ConnectionRefusedError,
    "TimeoutError": TimeoutError,
    "BrokenPipeError": BrokenPipeError,
}


def compute_delay_ms(
    attempt: int, base_delay_ms: float, max_delay_ms: float, jitter: bool
) -> float:
    """Compute the sleep before the *next* attempt. ``attempt`` is 1-indexed.

    Pure function so tests can pin behavior without sleeping.
    """
    raw = base_delay_ms * (2 ** (attempt - 1))
    delay = min(raw, max_delay_ms)
    if jitter:
        delay *= random.uniform(0.5, 1.5)
    return max(0.0, delay)


def with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 1,
    base_delay_ms: float = 200.0,
    max_delay_ms: float = 5000.0,
    jitter: bool = True,
    retryable: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn()`` with retry-on-transient-error semantics.

    Returns the function's value on success. Re-raises the *last* exception if
    every attempt fails, or re-raises immediately for non-retryable types.

    ``on_retry(attempt_number, delay_ms, exc)`` runs after a failure and before
    the sleep. Use it to emit a structured log event.

    ``sleep`` is injectable for tests so we don't actually wait.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except BaseException as exc:
            if not isinstance(exc, retryable):
                raise
            last_exc = exc
            if attempt >= attempts:
                break
            delay = compute_delay_ms(attempt, base_delay_ms, max_delay_ms, jitter)
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleep(delay / 1000.0)

    assert last_exc is not None  # only reachable after a retryable failure
    raise last_exc


def parse_retry_config(source_config: dict | None) -> dict:
    """Extract a kwargs dict for ``with_retry`` from a source-block ``retry:`` field.

    Missing/empty ``retry:`` returns ``{"attempts": 1}`` -- i.e. no retries.
    """
    if not source_config:
        return {"attempts": 1}
    cfg = source_config.get("retry") or {}
    if not cfg:
        return {"attempts": 1}
    return {
        "attempts": int(cfg.get("attempts", 1)),
        "base_delay_ms": float(cfg.get("base_delay_ms", 200.0)),
        "max_delay_ms": float(cfg.get("max_delay_ms", 5000.0)),
        "jitter": bool(cfg.get("jitter", True)),
        "retryable": _resolve_retryable(cfg.get("retryable")),
    }
