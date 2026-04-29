import os

from fidu.core.paths import resolve_in_package, resolve_relative


def test_resolve_relative_returns_absolute_for_relative():
    base = "/tmp/configs"
    resolved = resolve_relative(base, "../rules/orders.yaml")
    assert os.path.isabs(resolved)
    assert resolved.endswith(os.path.join("rules", "orders.yaml"))


def test_resolve_relative_passes_absolute_through():
    abs_path = "/var/log/dq.log"
    # Compare against the platform-normalized form: resolve_relative
    # round-trips absolute paths through os.path.normpath, which on Windows
    # converts forward slashes to backslashes. The test is verifying that
    # the absolute path is not joined with the base_dir, not that the
    # separator is preserved.
    assert resolve_relative("/anywhere", abs_path) == os.path.normpath(abs_path)


def test_resolve_in_package_finds_intelligence_files():
    path = resolve_in_package("intelligence", "rule_support_matrix.json")
    assert os.path.isfile(path)
