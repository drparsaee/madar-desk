# Madar LAN discovery: untrusted hints before pairing

`lan_discovery.py` is an opt-in UDP discovery helper for the existing authenticated
LAN host. It does **not** add accounts, authenticate users, approve devices, or
validate TLS identities. It does not open a socket on import.

## Integration API

Host, **after** successfully starting the HTTPS `LanService`:

```python
from lan_discovery import DiscoveryResponder

responder = DiscoveryResponder(
    host_name="Madar Office", host_port=48370, certfile=host_tls_certificate_path
)
responder.start()
# On host shutdown / switch of the active host:
responder.stop()
```

Client, in a user-triggered discovery operation:

```python
from lan_discovery import discover_hosts

candidates = discover_hosts(timeout=1.5, port=48371)
```

The host listens for solicits on **UDP 48371** and sends periodic beacons and
solicit responses to the client's **UDP 48372**. The TCP LAN HTTPS service
typically listens on **48370**, but `host_port` follows its actual configured
port. Beacons go to the local IPv4 broadcast address and do not cross routed
subnets. Solicit replies go to the source address and port observed by the
responder. Only RFC1918 source IPv4 addresses can become production candidates;
loopback is enabled only by private parameters for local tests.

Each candidate contains `name`, `url`, `fingerprint`, and `verified=False`, plus
`peer_ip`, `host_port`, `transport='https'`, `requires_pairing=True`,
`host_id`, `ttl` and `expires_at`. The HTTPS URL uses **the actual UDP peer IP**,
never an advertised URL or hostname. Candidates are capped at 32, protocol
datagrams at 512 bytes, and TTL at 15 seconds. Solicit replies echo a fresh
random nonce; server responses and announcements are rate-limited. The client
scans for no more than five seconds and bounds total received packets.

**Discovery is not trust.** Anyone on the LAN able to forge or spoof UDP
packets may advertise a false name, fake IP, or incorrect fingerprint. Treat
`fingerprint` as unverified display text only. Never pass it directly to
`lanJoin` or save it as an approved TLS pin just because discovery returned
it. The operator must verify the **full SHA-256 certificate fingerprint by an
independent trusted channel with the host**, and complete the existing host
account/PIN or explicit approval process as implemented by the integrating
application. A discovered host receives no authenticated access automatically.

The responder **requires an HTTPS certificate** and emits only
`transport='https'` candidates. HTTP-only hosts do not advertise themselves,
and clients neither attempt HTTP nor silently downgrade HTTPS. The integration
must preserve the current `pinned_https_json` certificate check before sending
credentials. Discovery neither verifies that HTTPS is actively listening nor
that the offered certificate matches the actual TLS listener.

Only enable the two discovery UDP ports for the Windows **Private** firewall
profile on a trusted local subnet. Never port-forward these ports. Run the
responder only while the authenticated HTTPS host is running; stop it when the
host stops. Peer discovery does not replace authorization, user permissions,
regular LAN connection handling, or the host's service lifecycle.

## Tests and limits

Run `python -m unittest tests.test_lan_discovery -v`. The tests use
`127.0.0.1`, ephemeral test ports, and a disposable public TLS test certificate
only. They exercise UDP solicit and passive beacons, packet/input rejection,
rate limits, TTL, Windows UDP error recovery and start/stop/restart. They send
**no actual LAN broadcasts**. Native bridge/GUI pairing, physical Windows
firewall environments, TLS end-to-end identity verification, multi-PC discovery
and authenticated host persistence require separate integration acceptance.
