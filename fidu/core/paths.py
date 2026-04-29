"""Path resolution helpers.

Goal: a config file references rules, data, and output paths *relative to its
own location*, so the runner works the same from any cwd (Airflow workers,
Streamlit, packaged install).
"""

import os


def package_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_relative(base_dir: str, path: str) -> str:
    """Resolve ``path`` against ``base_dir`` unless it is already absolute."""
    if path is None:
        return None
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(base_dir, path))


def resolve_in_package(*relative_parts: str) -> str:
    """Path inside the installed package (e.g. ``intelligence/*.json``)."""
    return os.path.join(package_root(), *relative_parts)
