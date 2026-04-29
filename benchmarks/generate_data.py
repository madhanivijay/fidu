"""Synthetic dataset generator for the benchmark suite.

The output schema is deliberately fixed so a benchmark run at 100K rows is
directly comparable to one at 10M rows: only the row count changes, the rule
set stays the same. Extra columns are padded in to hit a target column count
when callers want to stress wide schemas.

Schema (always present):

    order_id     int64    monotonically increasing, unique
    customer_id  float64  random; ~0.1% nulls injected
    amount       float64  uniform on [0, 1000]
    status       string   one of {new, shipped, delivered, canceled}
    email        string   user{i}@example.com
    created_at   datetime random within a 30-day window

Padding columns (only when ``cols`` exceeds 6):

    text_{i}     string   one of 4 categorical values
    num_{i}      float64  standard normal
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_BASE_COLUMNS = 6
_STATUSES = ["new", "shipped", "delivered", "canceled"]
_TEXT_FILL = ["alpha", "beta", "gamma", "delta"]


def generate(rows: int, cols: int = 50, seed: int = 42) -> pd.DataFrame:
    if rows <= 0:
        raise ValueError("rows must be positive")
    if cols < _BASE_COLUMNS:
        raise ValueError(f"cols must be >= {_BASE_COLUMNS}")

    rng = np.random.default_rng(seed)

    customer_id = rng.integers(1, max(2, rows // 10), size=rows).astype("float64")
    null_mask = rng.random(rows) < 0.001
    customer_id[null_mask] = np.nan

    base_offset = pd.Timestamp("2026-01-01")
    seconds_in_window = 86400 * 30
    created_at = base_offset + pd.to_timedelta(
        rng.integers(0, seconds_in_window, size=rows), unit="s"
    )

    df = pd.DataFrame(
        {
            "order_id": np.arange(rows, dtype=np.int64),
            "customer_id": customer_id,
            "amount": rng.uniform(0, 1000, size=rows),
            "status": rng.choice(_STATUSES, size=rows),
            "email": [f"user{i}@example.com" for i in range(rows)],
            "created_at": created_at,
        }
    )

    extras_needed = cols - _BASE_COLUMNS
    for i in range(extras_needed):
        if i % 2 == 0:
            df[f"text_{i}"] = rng.choice(_TEXT_FILL, size=rows)
        else:
            df[f"num_{i}"] = rng.normal(size=rows)
    return df
