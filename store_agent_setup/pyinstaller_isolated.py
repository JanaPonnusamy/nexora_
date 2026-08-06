"""Run PyInstaller with site-package discovery constrained to accessible paths."""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path


def _safe_existing_dirs(paths: list[str]) -> list[str]:
    safe_paths: list[str] = []
    for raw_path in paths:
        if not raw_path:
            continue
        try:
            path = Path(raw_path)
            if path.is_dir():
                safe_paths.append(str(path))
        except OSError:
            continue
        except PermissionError:
            continue
    return safe_paths


def _patch_site() -> None:
    original_getsitepackages = getattr(site, "getsitepackages", None)
    if callable(original_getsitepackages):
        def _wrapped_getsitepackages(prefixes=None):
            return _safe_existing_dirs(list(original_getsitepackages(prefixes)))

        site.getsitepackages = _wrapped_getsitepackages

    original_getusersitepackages = getattr(site, "getusersitepackages", None)
    if callable(original_getusersitepackages):
        def _wrapped_getusersitepackages():
            return ""

        site.getusersitepackages = _wrapped_getusersitepackages


def main() -> None:
    os.environ.setdefault("PYTHONNOUSERSITE", "1")
    _patch_site()
    from PyInstaller.__main__ import run

    run(sys.argv[1:])


if __name__ == "__main__":
    main()
