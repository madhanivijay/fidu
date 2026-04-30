"""Verify ``fidu.__version__`` is exposed and looks like a version string. 

When fidu is installed (``pip install fidu`` or ``pip install -e .``), the
version comes from package metadata — i.e. the ``version`` field in
``pyproject.toml``. When run from a source checkout without an install,
the fallback sentinel applies. Either way, the attribute must exist.
"""

import fidu


def test_version_attribute_exists():
    assert hasattr(fidu, "__version__"), "fidu must expose __version__"
    
    
def test_version_is_non_empty_string():
    assert isinstance(fidu.__version__, str)
    assert fidu.__version__, "__version__ must not be empty"