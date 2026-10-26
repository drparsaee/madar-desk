# -*- mode: python ; coding: utf-8 -*-
# R17 user titles + isolated Parsian test: new side-by-side executable. Never replace R15.
a = Analysis(
    ['standalone_accounting_desktop.py'],
    pathex=[], binaries=[], datas=[('dist', 'dist')],
    hiddenimports=['standalone_accounting_recovery_wizard',
                   'standalone_accounting_restore_ui',
                   'standalone_accounting_restore',
                   'standalone_accounting_company_registry',
                   'standalone_accounting_premium_chooser',
                   'standalone_accounting_identity',
                   'standalone_accounting_secure_login',
                   'standalone_accounting_user_dialog',
                   'standalone_accounting_tax_advisor',
                   'standalone_accounting_template_store'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Madar-Accounting-User-Roles-Parsian-Trial-R18-20261026',
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None,
    entitlements_file=None, icon=['assets/madar.ico'],
)
