# Madar Desk: Canonical Git

The only authoritative development source is the private LocalForge repository:

- Repository: http://127.0.0.1:3000/localadmin/madar-desk
- Default and canonical development branch: main
- This working directory (D:\CoS-Test\madar-desk) is a Git checkout of that repository, not an independent upstream.
- origin must refer only to LocalForge/Gitea. Do not publish to GitHub or use an alternate source-of-truth remote.
- Make source changes in this checkout, validate, commit, and push to LocalForge main. Other clones are disposable and never authoritative.

## Keep runtime and financial data out of Git

No private Parsian backups, staged financial imports, credentials, SQL/SQLite databases, operational backups, local QA work directories, or executable builds should be tracked in source Git.

Actual finance data and running executables remain in their existing local paths and require separate backed-up migration for any relocation. LocalForge Git version control is not itself a production database migration or application release.

See .gitignore for generated directories; never force-add private runtime data to bypass it.