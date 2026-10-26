# -*- mode: python ; coding: utf-8 -*-
# New disposable QA build. Never replace an installed R2 or its financial data.
a = Analysis(
    ['native_app.py'],
    pathex=[], binaries=[],
    datas=[('.qa-partial-return-vite-20261025', 'dist')],
    hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Madar-Desk-Fixes-R3-20261025',
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None,
    entitlements_file=None, icon=['assets/madar.ico'],
)
