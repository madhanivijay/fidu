"""Per-rule timeout helper.

Uses a worker thread + ``Future.result(timeout=)`` so the rule body runs in a
real Python thread that can be abandoned. The underlying work continues to
completion in the background -- there is no clean way to interrupt arbitrary
Python code -- so for warehouse engines you should *also* set a query-side
statement timeout. For in-process pandas this is best-effort: the timeout
returns control to the caller, the abandoned computation finishes whenever it
finishes.

This module is deliberately tiny and stdlib-only. Callers don't need to know
about ``ThreadPoolExecutor`` lifecycles -- just call ``run_with_timeout``.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RuleTimeoutError(TimeoutError):
    """Raised when a rule body exceeds its ``timeout_seconds`` budget."""


def run_with_timeout(fn: Callable[[], T], timeout_seconds: float) -> T:
    """Call ``fn()`` with a wall-clock timeout.

    Returns the function's value on success. Raises ``RuleTimeoutError`` if
    ``timeout_seconds`` elapses before the call returns. Re-raises any other
    exception thrown by ``fn`` unchanged.
    """
    if timeout_seconds is None or timeout_seconds <= 0:
        return fn()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise RuleTimeoutError(
                f"rule exceeded {timeout_seconds}s timeout"
            ) from exc
