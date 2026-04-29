"""Tests for the pluggable drift history backend.

The drift detector now talks to history through a ``HistoryBackend`` ABC
instead of poking files directly. These tests cover the three things that
matter:

* ``InMemoryHistoryBackend`` round-trips a full history dict and isolates
  callers (mutating the loaded dict must not bleed into the next load).
* ``FileHistoryBackend`` preserves the original recovery semantics — corrupt
  or malformed history is archived and the next run starts clean with a
  warning, instead of crashing.
* ``resolve_history_backend`` honours the documented precedence: explicit
  instance > dict spec with type > path-only fallback.
"""

import json
from pathlib import Path

import pytest

from fidu.drift.history_backend import (
    FileHistoryBackend,
    HistoryBackend,
    InMemoryHistoryBackend,
    register_history_backend,
    resolve_history_backend,
)


def test_in_memory_backend_round_trip():
    backend = InMemoryHistoryBackend()
    assert backend.load() == {"runs": []}

    backend.save({"runs": [{"run_timestamp": "2026-04-26T00:00:00Z"}]})
    loaded = backend.load()
    assert loaded["runs"][0]["run_timestamp"] == "2026-04-26T00:00:00Z"


def test_in_memory_backend_isolates_callers():
    """Mutating the loaded dict must not leak into the stored history."""
    backend = InMemoryHistoryBackend({"runs": [{"score": 100}]})
    snapshot = backend.load()
    snapshot["runs"].append({"score": 0})
    snapshot["runs"][0]["score"] = -1

    fresh = backend.load()
    assert fresh == {"runs": [{"score": 100}]}


def test_in_memory_backend_describe():
    assert InMemoryHistoryBackend().describe() == "memory://"


def test_file_backend_missing_file_returns_empty(tmp_path: Path):
    backend = FileHistoryBackend(str(tmp_path / "history.json"))
    assert backend.load() == {"runs": []}


def test_file_backend_save_and_load(tmp_path: Path):
    path = tmp_path / "nested" / "history.json"
    backend = FileHistoryBackend(str(path))

    backend.save({"runs": [{"project": "demo"}]})
    assert path.exists()

    loaded = backend.load()
    assert loaded == {"runs": [{"project": "demo"}]}


def test_file_backend_archives_corrupt_history(tmp_path: Path):
    path = tmp_path / "history.json"
    path.write_text("not valid json {{{")

    backend = FileHistoryBackend(str(path))
    result = backend.load()

    assert result["runs"] == []
    assert any("corrupt" in w for w in result.get("warnings", []))
    archived = list(tmp_path.glob("history.json.corrupt-*"))
    assert len(archived) == 1


def test_file_backend_archives_malformed_history(tmp_path: Path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps(["this", "is", "not", "a", "dict"]))

    backend = FileHistoryBackend(str(path))
    result = backend.load()

    assert result["runs"] == []
    assert any("malformed" in w for w in result.get("warnings", []))
    archived = list(tmp_path.glob("history.json.malformed-*"))
    assert len(archived) == 1


def test_file_backend_describe_includes_path(tmp_path: Path):
    path = tmp_path / "history.json"
    backend = FileHistoryBackend(str(path))
    assert backend.describe().startswith("file://")
    assert str(path) in backend.describe()


def test_resolve_returns_explicit_backend_instance():
    custom = InMemoryHistoryBackend({"runs": [{"marker": "explicit"}]})
    resolved = resolve_history_backend(
        history_path=None,
        drift_config={"history_backend": custom},
    )
    assert resolved is custom


def test_resolve_dict_spec_file(tmp_path: Path):
    path = tmp_path / "h.json"
    backend = resolve_history_backend(
        history_path=None,
        drift_config={"history_backend": {"type": "file", "path": str(path)}},
    )
    assert isinstance(backend, FileHistoryBackend)
    assert backend.path == str(path)


def test_resolve_dict_spec_file_falls_back_to_history_path(tmp_path: Path):
    """type=file with no explicit path uses the legacy history_path arg."""
    fallback = str(tmp_path / "fallback.json")
    backend = resolve_history_backend(
        history_path=fallback,
        drift_config={"history_backend": {"type": "file"}},
    )
    assert isinstance(backend, FileHistoryBackend)
    assert backend.path == fallback


def test_resolve_dict_spec_file_requires_path():
    with pytest.raises(ValueError, match="requires a 'path'"):
        resolve_history_backend(
            history_path=None,
            drift_config={"history_backend": {"type": "file"}},
        )


def test_resolve_dict_spec_memory():
    backend = resolve_history_backend(
        history_path=None,
        drift_config={
            "history_backend": {
                "type": "memory",
                "initial": {"runs": [{"seeded": True}]},
            }
        },
    )
    assert isinstance(backend, InMemoryHistoryBackend)
    assert backend.load()["runs"][0]["seeded"] is True


def test_resolve_default_is_file_backend(tmp_path: Path):
    path = str(tmp_path / "default.json")
    backend = resolve_history_backend(history_path=path, drift_config=None)
    assert isinstance(backend, FileHistoryBackend)
    assert backend.path == path


def test_resolve_requires_some_path_when_no_spec():
    with pytest.raises(ValueError, match="fidu.drift.history_path"):
        resolve_history_backend(history_path=None, drift_config=None)


def test_resolve_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown history backend"):
        resolve_history_backend(
            history_path=None,
            drift_config={"history_backend": {"type": "definitely-not-real"}},
        )


def test_resolve_custom_registered_backend():
    """External code can plug in a custom factory."""

    class TaggingBackend(HistoryBackend):
        def __init__(self, config):
            self.config = config
            self._history = {"runs": []}

        def load(self):
            return self._history

        def save(self, history):
            self._history = history

    register_history_backend("tagging-test", lambda config: TaggingBackend(config))

    backend = resolve_history_backend(
        history_path=None,
        drift_config={
            "history_backend": {"type": "tagging-test", "tag": "team-data"}
        },
    )
    assert isinstance(backend, TaggingBackend)
    assert backend.config == {"tag": "team-data"}
