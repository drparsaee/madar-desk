# LAN phase 2: reject ambiguous HTTP frames before routing

## Existing contract

`LanService.start()` exposes a loopback-only plaintext listener, requiring TLS
for non-loopback. Authentication, authorization and finance mutations are
implemented on the host; moving checks into a UI is not a security boundary.

## Evidence, change and limitations

- Integration routes already rejected duplicate HTTP header names and
  `Transfer-Encoding`. Regular `/api/` routes did not apply the same checks.
- A real synthetic HTTP request to `/api/login` with duplicate
  `Content-Length` was accepted (200) before the change, instead of 400.
- Moved both guards to the common `Handler.process()` before path dispatch,
  including the login and account routes. Duplicates are matched
  case-insensitively, and any `Transfer-Encoding` is rejected.
- New `tests.test_lan.LanTests.test_http_rejects_ambiguous_framing_and_duplicate_auth_headers`
  first failed, then passed after the fix. The broader LAN/accounting suite
  reported 148 tests `OK`, 2 expected failures.

This is a focused request-framing change, **not** proof of penetration-tested
network security, TLS certificate setup on actual two-PC installations or
complete host privilege coverage. Real accounts and services were untouched.
