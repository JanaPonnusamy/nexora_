"""Assemble a distributable release of the HO installer.

Collects the compiled ``release\\HO_Setup.exe`` (produced by Inno Setup via
build.bat) into a versioned folder + zip with a SHA-256 checksum, so a single
artifact can be handed to a tenant. ``package.bat`` is the batch equivalent.

    build.bat                  # PyInstaller + Inno -> release\\HO_Setup.exe
    python -m ho_setup.package  # then bundle it
"""
import hashlib
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from . import SETUP_EXE_NAME, __version__

REPO = Path(__file__).resolve().parent.parent
RELEASE = REPO / "release"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    setup_exe = RELEASE / SETUP_EXE_NAME
    if not setup_exe.is_file():
        raise SystemExit(
            f"{setup_exe} not found. Run build.bat (or ISCC installer\\HO_Setup.iss) "
            "first."
        )
    stamp = datetime.now().strftime("%Y%m%d")
    out_dir = RELEASE / f"UniNex_HO_{__version__}_{stamp}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    artifacts = [setup_exe]
    checksums = []
    for art in artifacts:
        shutil.copy2(art, out_dir / art.name)
        checksums.append(f"{_sha256(art)}  {art.name}")
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n",
                                            encoding="utf-8")

    zip_path = RELEASE / f"{out_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in out_dir.iterdir():
            zf.write(item, item.name)

    print("Release assembled:")
    print("  ", out_dir)
    print("  ", zip_path)
    for line in checksums:
        print("  ", line)


if __name__ == "__main__":
    main()
