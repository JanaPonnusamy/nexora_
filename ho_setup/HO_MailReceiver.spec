# -*- mode: python ; coding: utf-8 -*-
"""HO_MailReceiver.exe - standalone Windows-service host (onedir).

Phase 2 extraction: embeds Python + the EXISTING FILE_TRANSFER receiver
pipeline (modules.sync.file_transfer_scheduler/file_transfer_receiver_service/
file_transfer_transport.email) as bytecode -- no second receiver
implementation, just a second process able to host the same one.

Build (from anywhere):
    pyinstaller --noconfirm --clean ho_setup/HO_MailReceiver.spec
"""
import os

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.dirname(SPECPATH)            # noqa: F821 (SPECPATH injected)
BACKEND = os.path.join(REPO, "backend")

hiddenimports = [
    "pyodbc", "dotenv", "mail_receiver_main",
    "modules.sync.file_transfer_scheduler",
    "modules.sync.file_transfer_receiver_service",
    "modules.sync.file_transfer_transport.email",
    "modules.sync.file_transfer_transport.factory",
    "modules.sync.file_transfer_repository",
    "modules.sync.file_transfer_config",
    "ho_setup.mail_receiver_service",
    "ho_setup.service_manager",
]
for pkg in ("modules", "config"):
    hiddenimports += collect_submodules(pkg)

a = Analysis(
    [os.path.join(REPO, "ho_setup", "launch_mail_receiver_service.py")],
    pathex=[REPO, BACKEND],
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
    [],
    exclude_binaries=True,
    name="NexoraHOMailReceiver",
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
    name="NexoraHOMailReceiver",
)
