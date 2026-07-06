"""Build the three PyInstaller executables consumed by the Inno installer.

`build.bat` is the canonical one-command build (PyInstaller -> Inno Setup ->
release\\HO_Setup.exe). This module is the cross-platform-friendly equivalent of
the PyInstaller half, driving the spec files:

    python -m ho_setup.build            # build all three exes
    python -m ho_setup.build backend    # only HO_Backend
    python -m ho_setup.build deploy      # only HO_Deploy
    python -m ho_setup.build uninstall   # only HO_Uninstall

Outputs in E:\\Nexora\\dist\\:
    HO_Backend\\HO_Backend.exe   (onedir service host; embedded Python + backend)
    HO_Deploy.exe                (headless deployment helper)
    HO_Uninstall.exe             (standalone uninstaller)

Then compile the installer with Inno Setup:
    ISCC installer\\HO_Setup.iss   ->  release\\HO_Setup.exe
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "ho_setup"
DIST = REPO / "dist"
BUILD = REPO / "build"

_SPECS = {
    "backend": PKG / "HO_Backend.spec",
    "deploy": PKG / "HO_Deploy.spec",
    "uninstall": PKG / "HO_Uninstall.spec",
}


def _pyinstaller(spec):
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           str(spec)]
    print(">>", subprocess.list2cmdline(cmd))
    subprocess.run(cmd, check=True, cwd=str(REPO))


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found; installing...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"], check=True
        )


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    target = argv[0] if argv else "all"
    ensure_pyinstaller()
    DIST.mkdir(exist_ok=True)

    targets = list(_SPECS) if target == "all" else [target]
    for name in targets:
        if name not in _SPECS:
            raise SystemExit(f"unknown target {name!r}; choose from "
                             f"{', '.join(_SPECS)} or 'all'")
        _pyinstaller(_SPECS[name])

    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)

    print("\nArtifacts in", DIST)
    for item in sorted(DIST.iterdir()):
        kind = "dir " if item.is_dir() else "file"
        print(f"   [{kind}] {item.name}")
    print("\nNext: compile the installer with  ISCC installer\\HO_Setup.iss")


if __name__ == "__main__":
    main()
