# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['store_agent_setup.device_controller.service', 'store_agent_setup.device_controller.apps', 'store_agent_setup.device_controller.terminal', 'store_agent_setup.stock_client_host', 'modules.device_identity.crypto', 'modules.device_controller.protocol', 'win32timezone', 'win32com.client', 'win32gui', 'win32profile', 'win32ts']
hiddenimports += collect_submodules('cryptography')


block_cipher = None


a = Analysis(
    ['E:\\Nexora\\store_agent_setup\\launch_device_controller.py'],
    pathex=['E:\\Nexora', 'E:\\Nexora\\backend'],
    binaries=[],
    datas=[('E:\\Nexora\\backend\\config\\device_controller_command_key.pub.pem', '.'), ('E:\\Nexora\\backend\\config\\stock_release_signing_key.pub.pem', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter', 'fastapi', 'sqlalchemy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NexoraDeviceController',
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
