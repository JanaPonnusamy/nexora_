# -*- mode: python ; coding: utf-8 -*-
"""HO_Backend.exe - standalone Windows-service host (onedir).

Embeds Python + the entire FastAPI backend as bytecode, so the target machine
needs no Python and no backend source on disk.

Build (from anywhere):
    pyinstaller --noconfirm --clean ho_setup/HO_Backend.spec
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

REPO = os.path.dirname(SPECPATH)            # noqa: F821 (SPECPATH injected)
BACKEND = os.path.join(REPO, "backend")

datas, binaries, hiddenimports = [], [], ["pyodbc", "dotenv", "api.app"]

for pkg in ("uvicorn", "fastapi", "starlette", "pydantic", "anyio"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

for pkg in ("api", "config", "controllers", "dtos", "middleware",
            "models", "modules", "repositories", "services"):
    hiddenimports += collect_submodules(pkg)

a = Analysis(
    [os.path.join(REPO, "ho_setup", "launch_ho_service.py")],
    pathex=[REPO, BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
