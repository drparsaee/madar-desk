"""Create one disposable trial login, only after verified restored-BAK accounting import.

Creates no identity in R15/R16 or the original Parsian installation. The one
randomly generated credential is written only to the explicitly named private
QA folder so the owner can sign in and replace the test password afterward.
"""
from pathlib import Path
import json
import os
import secrets
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_desktop import AccountingDesktopAPI


def main():
    project=Path(__file__).resolve().parents[1]
    private=project/'.private-parsian-staging-20261026'/'migration-experiment-20261026'
    dest=private/'parsian-rial-gl-import-disposable'
    identity_file=dest/'local-users.json'
    credential=private/'R17-TRIAL-LOGIN-PRIVATE.txt'
    if (not dest.is_dir() or identity_file.exists() or credential.exists() or
        dest.is_symlink() or private.is_symlink()):
        raise RuntimeError('Refusing nonempty or non-disposable trial identity')
    report=json.loads((dest/'gl-import-audit.json').read_text(encoding='utf-8'))
    if (report.get('source')!='RESTORED_BAK_ISOLATED_VERIFIED_20261026' or
        report.get('bakSnapshotEquivalenceVerified') is not True or
        report.get('journalGroupsImported')!=124 or
        report.get('journalLinesImported')!=256 or
        report.get('safeToReplaceParsian') is not False):
        raise RuntimeError('Not the strictly checked restored BAK experiment')
    snap=AccountingDesktopAPI(dest).standaloneAccountingRead()
    historical=snap['view'].get('parsianMigration') or {}
    if (snap['revision']!=report['trialRevision'] or
        snap['view']['currency']!='RIAL' or
        historical.get('historicalInvoiceGroups')!=66):
        raise RuntimeError('Archived and posted trial source projections disagree')
    pwd=secrets.token_urlsafe(21)
    auth=LocalCompanyIdentity(dest)
    auth.add_user('trialadmin',pwd,'admin',job_title='مدیر ارشد')
    # The user must be able to inspect the generated trial login. Never write
    # the password into the app bundle, logs, real APPDATA or source code.
    with credential.open('x',encoding='utf-8') as file:
        file.write('حساب آزمایشی مدار از بکاپ پارسیان ۱۴۰۵/۰۸/۰۴ - فقط تست\n')
        file.write('نام کاربری: trialadmin\n')
        file.write('رمز عبور آزمایشی: '+pwd+'\n')
        file.write('پس از ورود، رمز آزمایشی را در مدیریت کاربران تغییر دهید.\n')
        file.write('این اطلاعات را با دیتابیس اصلی پارسیان اشتباه نگیرید.\n')
    try:os.chmod(credential,0o600)
    except OSError:pass
    token=auth.login('trialadmin',pwd)
    user=auth.require_session(token)
    view=AccountingDesktopAPI(dest,company_name='آزمایش بکاپ پارسیان ۱۵:۱۵',
        authenticated_user=user,identity_store=auth,
        identity_token=token).standaloneAccountingRead()
    auth.logout(token)
    if (view['revision']!=report['trialRevision'] or
        view['currentUser']['jobTitle']!='مدیر ارشد' or
        view['view']['parsianMigration']['historicalInvoiceGroups']!=66):
        raise RuntimeError('Final identity/ledger trial failed')
    print(json.dumps({'trialProfileReady':True,'username':'trialadmin',
        'credentialPath':str(credential),'authenticatedTrial':True,
        'journalCount':len(view['view']['journals']),
        'historicalInvoiceGroups':66,'source':'restored_backup_only'},ensure_ascii=False))


if __name__=='__main__':main()
