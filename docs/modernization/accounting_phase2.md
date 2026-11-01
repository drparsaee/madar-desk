# Independent accounting phase 2: bounded login input

## Existing business contract

`standalone_accounting_identity.py` stores identities separately from the
legacy TOMAN accounting store. Company registration accepts usernames matching
`_USER` and passwords of 4..256 characters without NUL. An existing login
path accepted oversized/NUL inputs and could persist failed-login lockout state.

## Characterization and change

- New test `test_login_rejects_credentials_outside_creation_limits` failed
  before the change because an invalid credential changed the disposable
  `local-users.json` lockout counters.
- Added the same username/password boundary validation to `login` before
  PBKDF2 and file mutation. Invalid inputs now fail with the existing generic
  `IdentityError('Authentication failed')`; valid-account behavior remains.
- The targeted test passed after the fix. A broader 148-test LAN/accounting
  suite and a separate 117-test finance/GL/rial suite passed. The 148-test
  suite included 2 intentionally expected failures.

No financial document, event schema, Parsian import, currency conversion,
historical opening balance, production database or transaction mutation was
altered. Financial migration still requires independent trial balance and
reconciliation approval.
