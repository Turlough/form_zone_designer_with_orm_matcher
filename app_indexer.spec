# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app_indexer.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Do not exclude numpy._pytesttester or numpy.testing — NumPy imports them at startup.
    excludes=[
        "pytest",
        "_pytest",
        "tkinter",
        "matplotlib",
        "IPython",
        "PyInstaller",
    ],
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
    name='app_indexer',
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
    icon='\\\\dddata\\output\\resource\\form_designer_configs\\app_icon.ico'
)
