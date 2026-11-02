# Accounting restore publication overview

Entrypoint: `restore_standalone_accounting(source, destination, plaintext_acknowledged=True, offline_acknowledged=True)` and its CLI in `standalone_accounting_restore.py`. Inputs are an explicitly named SQLite snapshot, optional `.users.json` and `.templates.json` siblings, plus an automatic-backup `.manifest.json` when applicable. Outputs in the already-existing destination directory are `standalone-accounting.sqlite3`, `local-users.json`, and `invoice-templates.json`.

Previously `_check_new_destination` and companion preview enforced no-clobber, SQLite backup and replay verified financial consistency, then independent hard links published SQLite and the two optional companions. This created an interruption window. Consumers open the SQLite and identity files by these existing final names; no runtime change or new consumer marker is planned.
