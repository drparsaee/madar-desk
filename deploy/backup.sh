#!/usr/bin/env bash
set -Eeuo pipefail

: "${MADAR_WEB_DB:?MADAR_WEB_DB is required}"
: "${MADAR_WEB_BACKUP_AGE_RECIPIENT:?Set an age public recipient before enabling backups}"

APP_ROOT="${MADAR_WEB_APP_ROOT:-/opt/madar-web}"
BACKUP_DIR="${MADAR_WEB_BACKUP_DIR:-/var/backups/madar-web}"
NODE_BIN="${NODE_BIN:-/usr/bin/node}"
AGE_BIN="${AGE_BIN:-/usr/bin/age}"
RCLONE_BIN="${RCLONE_BIN:-/usr/bin/rclone}"
RETENTION_DAYS="${MADAR_WEB_BACKUP_RETENTION_DAYS:-14}"
REMOTE="${MADAR_WEB_BACKUP_REMOTE:-}"

[[ "$RETENTION_DAYS" =~ ^[1-9][0-9]{0,2}$ ]] || {
  echo "MADAR_WEB_BACKUP_RETENTION_DAYS must be 1..999." >&2; exit 2;
}
[[ -x "$NODE_BIN" && -x "$AGE_BIN" ]] || {
  echo "Node.js or age executable is unavailable." >&2; exit 2;
}
[[ -f "$APP_ROOT/server/admin.cjs" ]] || {
  echo "Madar Web admin CLI was not found under MADAR_WEB_APP_ROOT." >&2; exit 2;
}

umask 077
install -d -m 0700 "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
work="$(mktemp -d "$BACKUP_DIR/.work.XXXXXX")"
plain="$work/backup.sqlite"
name="madar-web-$stamp.sqlite.age"
encrypted="$BACKUP_DIR/$name"
checksum="$encrypted.sha256"
trap 'rm -rf -- "$work"' EXIT

[[ ! -e "$encrypted" && ! -e "$checksum" ]] || {
  echo "Refusing to overwrite an existing backup." >&2; exit 3;
}

"$NODE_BIN" "$APP_ROOT/server/admin.cjs" backup "$plain"
"$AGE_BIN" -r "$MADAR_WEB_BACKUP_AGE_RECIPIENT" -o "$encrypted" "$plain"
chmod 0600 "$encrypted"
sha256sum "$encrypted" > "$checksum"
chmod 0600 "$checksum"

if [[ -n "$REMOTE" ]]; then
  [[ -x "$RCLONE_BIN" ]] || {
    echo "A backup remote is configured but rclone is unavailable." >&2; exit 4;
  }
  remote_file="${REMOTE%/}/$name"
  "$RCLONE_BIN" copyto "$encrypted" "$remote_file"
  "$RCLONE_BIN" copyto "$checksum" "$remote_file.sha256"
  local_hash="$(sha256sum "$encrypted" | awk '{print $1}')"
  remote_hash="$("$RCLONE_BIN" cat "$remote_file" | sha256sum | awk '{print $1}')"
  [[ "$local_hash" == "$remote_hash" ]] || {
    echo "Off-site backup checksum mismatch." >&2; exit 5;
  }
else
  echo "WARNING: encrypted local backup created; no off-site remote is configured." >&2
fi

find "$BACKUP_DIR" -maxdepth 1 -type f \
  \( -name 'madar-web-*.sqlite.age' -o -name 'madar-web-*.sqlite.age.sha256' \) \
  -mtime "+$RETENTION_DAYS" -delete

echo "Encrypted backup ready: $encrypted"
