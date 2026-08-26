"""Backend helpers for Playground application workflows."""

import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli
        sys.modules["tomllib"] = tomli
    except ImportError:
        pass
