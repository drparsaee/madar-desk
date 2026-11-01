# Madar isolated network laboratory

Run from the repository root on the Windows development machine:

```powershell
python tools/network_lab/lab.py run
python tools/network_lab/lab.py run --keep
python tools/network_lab/lab.py cleanup <32-character run ID>
python tools/network_lab/lab.py probe
```

`run` starts three **separate Windows Python processes**, each using its own
`APPDATA`, `LOCALAPPDATA`, `TEMP`, and `USERPROFILE` beneath a new
`tools/network_lab/.runs/<id>` directory. There is one real Madar `Bridge` and
`LanService` host bound **only** to `127.0.0.1` with an automatically assigned
TCP port and **HTTPS**. The two clients each use the application's real
`Bridge.lanJoin` and TLS certificate fingerprint validation. They act as an
editor scoped to the sample project and a viewer scoped to the personal
project. The lab checks a real editor commit, independent-process readback,
project scoping, client-side and host-side viewer write denial, a concurrent
pair of client processes, durable host file persistence, and rejection of a
wrong certificate pin.

The HTTPS certificate is the **known public TEST fixture** already in
`tests/test_lan_tls.py`. It is valid only for local isolated QA, never for
deployment, trusted networks, or anything involving real customer data.
Lab accounts and passwords are synthetic; passwords are generated anew for
every run and passed to the child processes via their environment (not via
command-line arguments). No production profiles or finance data are imported.

The runner signals the host to stop and waits for it to exit before removal.
By default, it deletes the complete synthetic run directory even on failure.
`--keep` retains the run directory, including synthetic client data and logs,
for diagnosis. A credential-free summary is saved to
`tools/network_lab/evidence/last-run.json` on every run. Use `cleanup` with
the printed run ID to delete a retained, stopped run. `.runs/` is Git-ignored.

## Virtualization preflight on the inspected Windows development machine

Read-only checks on 2026-11-01 showed Windows 10 Pro build 19045,
`HyperVisorPresent=True`, `Microsoft-Hyper-V-All=Disabled`,
`VirtualMachinePlatform=Enabled`, `Microsoft-Windows-Subsystem-Linux=Enabled`,
and a running **Debian WSL2** distribution. The `vmcompute` service was
running. This is evidence WSL2 is usable, **not evidence that Windows Hyper-V
Manager can currently create full Windows VMs**. No OS features were enabled,
no VM/Docker/container installed, no firewall rules changed, and no Windows
services created. Windows-to-WSL2 communication is a separate test owned by
the other network-lab worker.

This topology is **process and profile isolation on one Windows host**, not
three operating systems or three physical network nodes. Its checks cannot
substitute for real two-PC acceptance covering physical LAN discovery,
certificate deployment, OS logins, network changes, power loss or firewall.

## Extended three-client scenario and UI checks

From repository root:

~~~powershell
python tests/network_lab/run_multi_client.py
node --test --test-concurrency=1 tests/madar_lan_pairing_ui_runtime.test.cjs tests/madar_lan_user_ui_runtime.test.cjs tests/sync_health.test.cjs tests/native_bridge_readiness.test.cjs
~~~

The extended scenario runs three independent real Bridge client processes:
two editors and one viewer. They use separate synthetic profiles and the
real HTTPS LanService host, exercising permissions, TLS pinning, concurrent
revision conflicts, offline queue/replay, and host/client restart. Results
are written to tests/network_lab/evidence_latest.json; synthetic profiles
are deleted automatically. An independently repeated run passed 35 of 35
checks. This is one Windows OS, NOT three Windows VMs.

Debian WSL2 was also probed as a separate-OS client. Its TLS request to the
Windows host on 172.19.240.1 timed out (OpenSSL exit 124, no HTTP bytes),
even with a narrowly restricted temporary Windows inbound firewall rule.
The temporary rule was removed and absence checked. This cross-OS case
remains UNVERIFIED; do not present it as passing.
