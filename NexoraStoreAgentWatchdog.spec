# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['store_agent_setup.watchdog_service', 'store_agent_setup.service_manager', 'win32timezone', 'pyodbc', 'store_agent.run_agent', 'store_agent.run_sync_runtime']
hiddenimports += collect_submodules('store_agent')


a = Analysis(
    ['E:\\Nexora\\store_agent_setup\\launch_watchdog_service.py'],
    pathex=['E:\\Nexora'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter'],
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
    name='NexoraStoreAgentWatchdog',
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
