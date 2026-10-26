# -*- mode: python ; coding: utf-8 -*-
# R11 preview: safe company switch, explicit catalog search and paired
# template+ledger offline restore. Prior releases must never be replaced.
a = Analysis(
    ['standalone_accounting_desktop.py'],
    pathex=[], binaries=[], datas=[('dist', 'dist')],
    hiddenimports=['standalone_accounting_recovery_wizard',
                   'standalone_accounting_restore_ui',
                   'standalone_accounting_restore',
                   'standalone_accounting_company_registry',
                   'standalone_accounting_template_store'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Madar-Accounting-Mohsen-UX-R11-20261025',
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None,
    entitlements_file=None, icon=['assets/madar.ico'],
)
