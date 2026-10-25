# Madar LAN transport security (implementation handoff)

## Status

`lan.py` supports an **opt-in TLS listener** and a pinned HTTPS JSON client helper.
`native_app.py` now supports HTTPS host configuration and fingerprint-pinned
HTTPS connections; the desktop LAN dialog exposes certificate/key paths for
hosts and a full SHA-256 fingerprint field for clients. Legacy HTTP remains
available and must be treated as **unencrypted**.

## API

```python
from lan import LanService, certificate_fingerprint, pinned_https_json

host = LanService(bridge, users_file, bind="0.0.0.0", port=48370,
                  certfile=r"C:\private\madar-cert.pem",
                  keyfile=r"C:\private\madar-key.pem")
port = host.start()  # HTTPS listener with TLS 1.2+; stop() closes it
print(certificate_fingerprint(r"C:\private\madar-cert.pem"))

# A client must receive this SHA-256 fingerprint over a separate trusted
# channel, such as direct comparison with the host's printed fingerprint.
login = pinned_https_json("https://192.168.1.20:48370/api/login", fingerprint,
                          method="POST", data={"username": user, "password": password})
state = pinned_https_json("https://192.168.1.20:48370/api/state", fingerprint,
                          headers={"Authorization": "Bearer " + login["token"]})
```

`certificate_fingerprint` hashes the leaf certificate's DER encoding. The
pin is a complete 64-character SHA-256 hex value, optionally written as 32
colon-separated bytes. `pinned_https_json` accepts only `https://` URLs to
private/loopback numeric IPs with explicit ports. It validates the presented
certificate over the *same TLS connection before transmitting* the HTTP
request, including credentials and bearer tokens. Failed pin verification
raises `ssl.SSLCertVerificationError`; there is **no unpinned retry, HTTP
downgrade, CA-only bypass or redirected request**. Non-2xx responses raise
`urllib.error.HTTPError` so the existing Bridge's 401/403/409 error
translation can be reused.

The client deliberately accepts a self-signed certificate **only when its
fingerprint matches the provided pin**. This is certificate pinning, not CA
trust or hostname validation. A replaced/reissued certificate requires
explicit re-pairing. The private key never belongs on client PCs.

TLS listener setup requires both `certfile` and `keyfile`. It raises on a
missing, corrupt or mismatched pair before the listener is exposed. With
neither provided it preserves legacy plain HTTP; operators must opt in.

## Certificate issuance example

With OpenSSL installed, use a unique key on the host, replacing the address
with its actual reserved LAN IP:

```powershell
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 -keyout madar-key.pem -out madar-cert.pem -subj "/CN=madar-host" -addext "subjectAltName=IP:192.168.1.20"
```

Store the PEM private key with Windows ACLs granting access only to the host
account. Do not use the disposable test certificate/private key from
`tests/test_lan_tls.py` for a deployment. Share only the fingerprint using an
authenticated, preferably out-of-band channel. Protect the fingerprint
against tampering: an attacker-supplied fingerprint defeats pairing.

## Native host integration (implemented locally; physical acceptance pending)

The following integration points are implemented in `native_app.py`; they
remain useful as a maintenance and QA checklist.

1. **Bridge init:** pass previously configured server
   `certfile` and `keyfile` to `LanService(...)` on restart, when TLS mode is
   enabled. Treat unavailable cert/key as an error; do not restart an intended
   TLS service as HTTP.
2. **`lanHost`:** accept explicit transport/certificate
   configuration and provide `certfile` and `keyfile` to `LanService`.
   Persist transport and certificate file references with the server config
   for restart. If a listener already exists, switching transport requires
   explicitly stopping/restarting it.
3. **`_remote_request`:** for configured `https://`
   client URLs, call `pinned_https_json(base + endpoint, fingerprint,
   method=..., data=..., headers=...)`. Require a stored SHA-256 pin. Keep
   `http_json` for legacy `http://` and for non-LAN Google APIs. Handle
   `HTTPError` status codes 401/403/409 exactly as `http_json` already
   does. Do not catch a pin mismatch and retry with `http_json`.
4. **`_remote_login`:** extend the previous HTTP-only
   scheme validator for HTTPS with an explicitly provided or saved pin. Store
   the pin into the temporary client connection *before* the first login
   request so the credential-bearing request is verified.
5. **`lanJoin` and client startup:**
   accept user-confirmed pin, save it alongside the HTTPS URL in
   `lan-connection.json`, and restore the saved pin before login on restart.
   Do not allow `https` without a pin. If a secure host is unavailable,
   preserve offline behavior, never silently downgrade to HTTP.
6. **UI and packaging:** show transport and fingerprint pairing explicitly.
   Confirm `LAN_TLS.md` is included in source archives if distributed.
   Update `NETWORK.md` and README only after an integrated build is
   verified.

## Persistence integration

Three LAN mutation paths now use `LanService._commit_domain`:
`collab_command`, `finance_command` and `run_scheduler`. It delegates to
`Bridge._commit_domain(domain, state)` when available, to use Prime's
transactional persistence. Without that Bridge method, it uses the legacy
per-domain JSON atomic write. When the Bridge method raises, the exception
propagates without silently saving stale JSON.

## Verification scope

`python -m unittest discover -s tests -p test_lan_tls.py -v` tests a real
loopback HTTPS listener using a disposable, static self-signed test key;
successful login/read, authenticated failures, pin mismatch before login,
invalid pin / unencrypted URL rejection, missing-key failure and transactional
commit delegation. These tests do **not** verify the desktop UI, real Windows
deployment, certificate provisioning/rotation on two PCs, or the not-yet-wired
`native_app.py` client integration. Further `tests/test_native_tls.py` cover
host restart and Bridge login over pinned HTTPS. Real two-PC deployment and
certificate provisioning/rotation still require manual acceptance.
