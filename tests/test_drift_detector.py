import json

from fidu.drift import drift_detector
from fidu.drift.history_backend import FileHistoryBackend


def test_file_backend_archives_corrupt_history(tmp_path):
    """Replaces the old ``_safe_load_history`` test — the recovery semantics
    now live on ``FileHistoryBackend.load`` but the behavior is identical:
    bad files get archived and we hand back an empty history with a warning
    so the next run can still execute drift detection."""
    history = tmp_path / "history.json"
    history.write_text("{ not valid json")

    loaded = FileHistoryBackend(str(history)).load()

    assert loaded["runs"] == []
    assert any("corrupt" in w for w in loaded.get("warnings", []))
    archived = list(tmp_path.glob("history.json.corrupt-*"))
    assert archived, "expected corrupt file to be archived"


def test_file_backend_returns_runs_for_valid_json(tmp_path):
    history = tmp_path / "history.json"
    history.write_text(json.dumps({"runs": [{"run_timestamp": "x", "datasets": []}]}))

    loaded = FileHistoryBackend(str(history)).load()

    assert len(loaded["runs"]) == 1


def test_infer_columns_prefers_columns_seen():
    dataset = {
        "columns_seen": ["a", "b"],
        "results": [{"column": "ignored", "details": {"actual_columns": ["xx"]}}],
    }
    assert drift_detector.infer_columns_from_dataset(dataset) == ["a", "b"]


def test_infer_columns_falls_back_to_results():
    dataset = {
        "results": [
            {"column": "a"},
            {"columns": ["b", "c"]},
            {"details": {"actual_columns": ["d"]}},
        ]
    }
    assert drift_detector.infer_columns_from_dataset(dataset) == ["a", "b", "c", "d"]


def test_safe_score_drop_handles_none():
    assert drift_detector._safe_score_drop(None, 90) is None
    assert drift_detector._safe_score_drop(95, None) is None
    assert drift_detector._safe_score_drop(95, 80) == 15
