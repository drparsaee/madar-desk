# Madar Desktop 1.0.26: integrated P1 + P2 update

## Scope and lineage

- Built on the isolated 1.0.25 P1 candidate branch `41dcf41`, itself
  descended from the frozen 1.0.24 P0 candidate.
- Cherry-picked the approved P2 Native commits `d95bb0e` through `32bd8ff`
  and the nonduplicate Web P2 commits `821a703` and `3126f3e`.
  Earlier Web parity changes were already included by Native P2 changes;
  duplicate cherry-picks `450d6b9` and `b44d9bd` were skipped.
- Retains distinct Native desktop and Web/PWA backend implementations;
  no Taraz accounting service or stored customer data is bundled or deployed.

## User-visible P2 features included

- Authorized notification navigation and accessible read/unread actions.
- Scoped @mention suggestions in project/card conversations.
- Gantt dependency overlap warnings with guarded one-card correction.
- Visible-scope critical-path analysis with explicit limits.
- Impact preview before accepting an individual Gantt drag.
- Server-owned, read-only LAN and Web Gantt shift preflight.

Bulk, atomic, multi-card schedule changes are **not** implemented or advertised.
Host preflight does not commit changes. The Web server/PWA needs its own
deployment and is not activated by installing the desktop EXE.

## Automatic update behavior

- 1.0.26 starts a GitHub release check when the Windows desktop opens.
- If a new stable version exists, it **downloads and validates** the trusted
  installer in the local update cache automatically.
- A failed download remains retryable with the explicit update button.
- **Installation is not automatic:** the user must choose installation,
  which runs the verified Inno setup only after the app exits and performs
  a protected backup.
- Public versions through 1.0.23 only **check** at startup. Their first
  upgrade to 1.0.26 needs one explicit download/install action.
- Release metadata and assets are accepted only from
  `drparsaee/madar-desk-updates`; the Windows setup asset name must be
  `Madar-Desk-1.0.26-Setup.exe`.

## QA and release limitations

This is a versioned integration candidate, not evidence of full production
qualification. Tests and checks must be recorded after building against
the exact resulting binaries. The legacy full Python regression still has
unclassified failures; a clean subset is not a waiver. Physical two-PC LAN,
real external customer installations, and signed Windows distribution have
not been confirmed. Never overwrite an earlier immutable 1.0.24 or 1.0.25
candidate, or silently modify the live user profile during QA.
