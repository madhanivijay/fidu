"""fidu — tool-agnostic data quality runner."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fidu")
except PackageNotFoundError:
    # Package isn't installed (e.g. running directly from a source checkout
    # without `pip install -e .`). Fall back to a sentinel so importing
    # ``fidu`` still works for development.
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]