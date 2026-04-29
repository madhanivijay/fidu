"""Worked example: a custom JSON Lines connector.

Demonstrates the three things every plugin needs:

    1. Subclass the kit's base interface (here: ``BaseConnector``)
    2. Implement the contract method(s) (here: ``load_data``)
    3. Register a factory with the registry (here: ``register_connector``)

Once registered, configs can refer to ``type: jsonl`` and the executor will
dispatch to this class -- no changes to ``main.py`` or core modules needed.

JSONL is deliberately a small, real format the kit doesn't ship out of the
box, so this example doubles as a useful adapter, not just a teaching toy.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd

from fidu.connectors.base_connector import BaseConnector
from fidu.connectors.connector_factory import register_connector


class JSONLConnector(BaseConnector):
    """Read newline-delimited JSON into a DataFrame.

    Supports plain ``.jsonl`` and gzipped ``.jsonl.gz`` paths.
    """

    def load_data(self, source_config: dict) -> pd.DataFrame:
        path = source_config["path"]
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        return pd.DataFrame.from_records(records)


def install() -> None:
    """Register the JSONL connector with the kit.

    Call this once at process start (e.g. in your Airflow plugin's __init__,
    or in the entry point of an embedding service). After this, any rule file
    can use ``type: jsonl`` in its ``source:`` block.
    """
    register_connector("jsonl", lambda: JSONLConnector(), aliases=["json_lines"])


__all__ = ["JSONLConnector", "install"]


if __name__ == "__main__":  # pragma: no cover - small demo runner
    import sys
    import tempfile

    install()

    sample = [
        {"order_id": 1, "amount": 50.0, "status": "PLACED"},
        {"order_id": 2, "amount": 99.5, "status": "DELIVERED"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "demo.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in sample), encoding="utf-8")

        from fidu.connectors.connector_factory import get_connector
        df = get_connector("jsonl").load_data({"path": str(p)})
        print(df)
        sys.exit(0)
