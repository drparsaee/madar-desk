# MD-O15 overview

Entry points: periodic/exit `AutomaticStandaloneBackups.backup_now()` in `standalone_accounting_auto_backup.py`, explicit `restore_standalone_accounting()` and CLI in `standalone_accounting_restore.py`. Persistence: a SQLite snapshot in `standalone-accounting-backups/`, optionally a JSON template library and a JSON hashed-password user registry. Backup retention is bounded and serialized with a directory lock. The manual backup exporter in `standalone_accounting_backup.py` is separate and preserves a single SQLite snapshot.
