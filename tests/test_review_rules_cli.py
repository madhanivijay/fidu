import os
import subprocess
import sys

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(REPO_ROOT, "fidu", "tools", "review_rules.py")


def _run(args, expect_success=True):
    proc = subprocess.run(
        [sys.executable, SCRIPT, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if expect_success:
        assert proc.returncode == 0, proc.stderr
    return proc


def _write_rules(tmp_path, rules):
    p = tmp_path / "rules.yaml"
    p.write_text(yaml.safe_dump({"rules": rules}, sort_keys=False))
    return str(p)


def test_list_action_prints_rules(tmp_path):
    path = _write_rules(
        tmp_path,
        [{"name": "r1", "type": "not_null", "column": "id"}],
    )
    proc = _run(["--file", path, "--action", "list"])
    assert "r1" in proc.stdout


def test_approve_with_out_of_range_index_fails_gracefully(tmp_path):
    path = _write_rules(
        tmp_path,
        [{"name": "r1", "type": "not_null", "column": "id"}],
    )
    proc = _run(["--file", path, "--action", "approve", "--index", "99"], expect_success=False)
    assert proc.returncode != 0
    assert "out of range" in proc.stderr.lower()


def test_approve_missing_index_fails_gracefully(tmp_path):
    path = _write_rules(
        tmp_path,
        [{"name": "r1", "type": "not_null", "column": "id"}],
    )
    proc = _run(["--file", path, "--action", "approve"], expect_success=False)
    assert proc.returncode != 0
    assert "1-based" in proc.stderr.lower() or "index" in proc.stderr.lower()


def test_approve_action_updates_review_status(tmp_path):
    path = _write_rules(
        tmp_path,
        [{"name": "r1", "type": "not_null", "column": "id", "draft": True}],
    )
    _run(["--file", path, "--action", "approve", "--index", "1"])
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["rules"][0]["review_status"] == "approved"
    assert data["rules"][0]["draft"] is False


def test_missing_file_raises_friendly_error(tmp_path):
    proc = _run(
        ["--file", str(tmp_path / "nope.yaml"), "--action", "list"],
        expect_success=False,
    )
    assert proc.returncode != 0
    assert "not found" in proc.stderr.lower()
