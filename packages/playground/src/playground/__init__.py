"""Playground core library."""

import os
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli
        sys.modules["tomllib"] = tomli
    except ImportError:
        pass


def _load_env_local() -> None:
    current = Path(__file__).resolve().parent
    # Search upwards from current file to find repo root
    search_dirs = [current] + list(current.parents)
    for directory in search_dirs:
        for candidate in (directory / ".env.local", directory / "application" / "playground" / ".env.local"):
            if candidate.is_file():
                try:
                    for line in candidate.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            os.environ.setdefault(k, v)
                except Exception:
                    pass


_load_env_local()
