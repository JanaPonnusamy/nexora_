# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\Nexora\\store_agent_setup\\launch_wizard.py'],
    pathex=['E:\\Nexora'],
    binaries=[],
    datas=[('E:\\Nexora\\dist\\NexoraStoreAgent', 'agent'), ('E:\\Nexora\\dist\\NexoraStoreAgentSettings.exe', '.')],
    hiddenimports=[],
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
    name='NexoraStoreAgentSetup',
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
