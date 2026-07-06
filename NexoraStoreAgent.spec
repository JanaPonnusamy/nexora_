# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['win32timezone', 'pyodbc', 'store_agent.run_agent', 'store_agent.run_sync_runtime']
hiddenimports += collect_submodules('store_agent')


a = Analysis(
    ['E:\\Nexora\\store_agent_setup\\launch_agent_service.py'],
    pathex=['E:\\Nexora'],
    binaries=[],
    datas=[('E:\\Nexora\\store_agent\\config\\fernet.key', 'store_agent/config')],
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
    name='NexoraStoreAgent',
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
    name='NexoraStoreAgent',
)
