#!/usr/bin/env bash
set -Eeuo pipefail

origin="${1:?Usage: smoke.sh https://your-domain.example}"
[[ "$origin" == https://* && "$origin" != */ ]] || {
  echo "Use the exact public HTTPS origin without a trailing slash." >&2; exit 2;
}

health="$(curl --fail --silent --show-error --max-time 10 "$origin/api/web/v1/health")"
node -e 'const h=JSON.parse(process.argv[1]);if(h.service!=="madar-web-api"||h.contract!=="madar-web-api-v1"||h.status!=="ready")process.exit(1)' "$health"
headers="$(curl --fail --silent --show-error --head --max-time 10 "$origin/")"
printf '%s\n' "$headers" | grep -qi '^content-type: text/html' || {
  echo 'The PWA root did not return HTML.' >&2; exit 3;
}
printf '%s\n' "$headers" | grep -qi '^x-content-type-options: nosniff' || {
  echo 'The static security headers are missing.' >&2; exit 4;
}
printf '%s\n' "$headers" | grep -qi '^strict-transport-security:' || {
  echo 'HSTS is missing from the public HTTPS response.' >&2; exit 5;
}
echo 'Public HTTPS smoke passed: PWA HTML, API readiness and security headers.'
