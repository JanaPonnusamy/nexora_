# -*- mode: python ; coding: utf-8 -*-
"""HO_Backend.exe - standalone Windows-service host (onedir).

Embeds Python + the entire FastAPI backend as bytecode, so the target machine
needs no Python and no backend source on disk.

Build (from anywhere):
    pyinstaller --noconfirm --clean ho_setup/HO_Backend.spec
"""
import glob
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

REPO = os.path.dirname(SPECPATH)            # noqa: F821 (SPECPATH injected)
BACKEND = os.path.join(REPO, "backend")

# Lite HO build: the document_extraction module's OCR engine (paddleocr) and
# its cv2 preprocessing step are the only backend consumers of this ML stack
# (see backend/modules/document_extraction/ocr/paddle_engine.py and
# preprocessing.py). Excluding them keeps HO_Backend under Inno Setup's
# 4.2GB single-file limit; api/app.py already degrades gracefully (router is
# None) when this import fails, so the rest of the API is unaffected.
ML_EXCLUDES = [
    "paddle", "paddleocr", "paddlepaddle", "torch", "torchvision", "torchaudio",
    "cv2", "opencv", "tensorflow", "jax", "jaxlib", "triton",
    "IPython", "jupyter", "notebook", "pytest", "gunicorn",
    "numba", "llvmlite", "transformers", "sentencepiece",
    "skimage", "albumentations", "albucore", "shapely", "pyclipper", "lmdb",
]

datas, binaries, hiddenimports = [], [], ["pyodbc", "dotenv", "api.app"]

for pkg in ("uvicorn", "fastapi", "starlette", "pydantic", "anyio"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

for pkg in ("api", "config", "controllers", "dtos", "middleware",
            "models", "modules", "repositories", "services"):
    hiddenimports += collect_submodules(pkg)

# Non-.py resources (module-owned migration SQL, e.g. agent_ops/sql,
# licensing/sql) aren't picked up by collect_submodules above - it only
# gathers importable modules. Modules read these at runtime relative to
# __file__, so without this they're silently missing from _internal and
# every call that touches them throws (see agent_ops.repository.ensure_schema).
for sql_dir in glob.glob(os.path.join(BACKEND, "modules", "*", "sql")):
    module_name = os.path.basename(os.path.dirname(sql_dir))
    for sql_file in glob.glob(os.path.join(sql_dir, "*.sql")):
        datas.append((sql_file, os.path.join("modules", module_name, "sql")))

# Release-signing PUBLIC key, so an exe HO node can verify (sha256 + Ed25519) a
# pulled backend bundle before swapping it (modules.ho_ops.service._public_key
# reads it from sys._MEIPASS). The private half is never bundled.
_pub = os.path.join(BACKEND, "config", "stock_release_signing_key.pub.pem")
if os.path.isfile(_pub):
    datas.append((_pub, "."))

a = Analysis(
    [os.path.join(REPO, "ho_setup", "launch_ho_service.py")],
    pathex=[REPO, BACKEND],
    binaries=binaries,
    datas=datas,
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
    [],
    exclude_binaries=True,
    name="HO_Backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HO_Backend",
)
