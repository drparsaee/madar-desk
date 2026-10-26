# -*- mode: python ; coding: utf-8 -*-
# Immutable R5 accounting release candidate; never replace older EXEs.
a = Analysis(
    ['standalone_accounting_desktop.py'],
    pathex=[], binaries=[],
    datas=[('.qa-accounting-r5-20261025', 'dist')],
    hiddenimports=['standalone_accounting_recovery_wizard'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Madar-Accounting-Fixes-R5-20261025',
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None,
    entitlements_file=None, icon=['assets/madar.ico'],
)
