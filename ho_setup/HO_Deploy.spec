# -*- mode: python ; coding: utf-8 -*-
"""HO_Deploy.exe - headless deployment helper (onefile console).

Driven by the Inno installer to test SQL, write config, restore the .bak,
install the Windows service, run the health check and uninstall.

Build:
    pyinstaller --noconfirm --clean ho_setup/HO_Deploy.spec
"""
import os

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.dirname(SPECPATH)            # noqa: F821 (SPECPATH injected)

hiddenimports = ["pyodbc", "requests", "dotenv", "win32timezone"]
hiddenimports += collect_submodules("ho_setup")

# This helper never touches backend/modules (OCR/paddleocr/torch) -- exclude
# them explicitly in case PyInstaller's graph walk reaches them via the
# shared, non-isolated Python environment (see HO_Backend.spec for why).
ML_EXCLUDES = [
    "paddle", "paddleocr", "paddlepaddle", "torch", "torchvision", "torchaudio",
    "cv2", "opencv", "tensorflow", "jax", "jaxlib", "triton",
    "IPython", "jupyter", "notebook", "pytest", "gunicorn",
    "numba", "llvmlite", "transformers", "sentencepiece",
    "skimage", "albumentations", "albucore", "shapely", "pyclipper", "lmdb",
]

a = Analysis(
    [os.path.join(REPO, "ho_setup", "launch_deploy.py")],
    pathex=[REPO],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=ML_EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HO_Deploy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
