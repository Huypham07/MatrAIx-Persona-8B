"""Playground shared utilities."""

import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli
        sys.modules["tomllib"] = tomli
    except ImportError:
        pass

from pkgutil import extend_path

# Allow environment/agents/matraix to contribute agent modules when both roots
# are on PYTHONPATH.
__path__ = extend_path(__path__, __name__)

__version__ = "0.1.0"

