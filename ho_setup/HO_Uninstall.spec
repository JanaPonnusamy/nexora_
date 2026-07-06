# -*- mode: python ; coding: utf-8 -*-
"""HO_Uninstall.exe - standalone uninstaller (onefile, windowed).

Removes the Windows service and application files; preserves the SQL database
unless explicitly told to drop it.

Build:
    pyinstaller --noconfirm --clean ho_setup/HO_Uninstall.spec
"""
import os

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.dirname(SPECPATH)            # noqa: F821 (SPECPATH injected)

hiddenimports = ["pyodbc", "win32timezone"]
hiddenimports += collect_submodules("ho_setup")

a = Analysis(
    [os.path.join(REPO, "ho_setup", "launch_uninstall.py")],
    pathex=[REPO],
    binaries=[],
    datas=[],
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
    a.binaries,
    a.datas,
    [],
    name="HO_Uninstall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
