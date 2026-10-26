"""Provision a separate, one-time identity for the migrated-customer QA book.

Never access real accounts or clone another company's identity registry.
The full credentials are written once to a private owner-only file, not stdout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone_accounting_desktop import AccountingDesktopAPI
from standalone_accounting_identity import LocalCompanyIdentity


def main():
    project = Path(__file__).resolve().parents[1]
    experiment = (project / '.private-parsian-staging-20261026' / 'r19-1405'
                  / 'migration-experiment-20261026')
    book = experiment / 'parsian-operational-customer-test-disposable'
    credential = experiment / 'R19-50-CUSTOMERS-LOGIN-PRIVATE.txt'
    if (not book.is_dir() or book.is_symlink()
            or credential.exists() or (book / 'local-users.json').exists()):
        raise RuntimeError('Refusing to modify existing trial identity or non-private book')
    audit_file = book / 'customer-registration-audit.json'
    audit = json.loads(audit_file.read_text(encoding='utf-8'))
    if (audit.get('customerIdentityCount') != 50
            or audit.get('oldGLDocumentsRetained') != 125
            or audit.get('historicGLReposted') is not False
            or audit.get('bookRevision') != 301):
        raise RuntimeError('Customer registration proof does not match R19 trial')
    before = AccountingDesktopAPI(book).standaloneAccountingRead()
    if (before['revision'] != 301
            or len(before['view']['parties']) != 50
            or len(before['view']['journals']) != 125
            or len(before['view']['items']) != 88
            or before['view']['currency'] != 'RIAL'):
        raise RuntimeError('Unexpected financial book before trial user provision')

    password = secrets.token_urlsafe(24)
    identity = LocalCompanyIdentity(book)
    identity.add_user('trialadmin50', password, 'admin', job_title='مدیر ارشد')
    with credential.open('x', encoding='utf-8') as out:
        out.write('فقط حساب آزمایشی پارسیان با ۵۰ شخص / هر دو سال مالی\n')
        out.write('نام کاربری: trialadmin50\n')
        out.write('رمز عبور آزمایشی: ' + password + '\n')
        out.write('اطلاعات شخصی/مالی این دفتر آزمایشی است؛ رمز را در مدیریت کاربران عوض کنید.\n')
    try:
        os.chmod(credential, 0o600)
    except OSError:
        pass

    token = identity.login('trialadmin50', password)
    try:
        account = identity.require_session(token)
        verified = AccountingDesktopAPI(book, authenticated_user=account,
            identity_store=identity, identity_token=token).standaloneAccountingRead()
        if (verified['revision'] != before['revision']
                or verified['currentUser']['role'] != 'admin'
                or verified['currentUser']['jobTitle'] != 'مدیر ارشد'):
            raise RuntimeError('Trial authentication changed financial state')
    finally:
        identity.logout(token)

    print(json.dumps({'separateTrialIdentityCreated': True,
        'username': 'trialadmin50', 'credentialPath': str(credential),
        'trialBookRevision': verified['revision'], 'parties': 50,
        'financialChangesMadeByProvision': 0}, ensure_ascii=True))


if __name__ == '__main__':
    main()
