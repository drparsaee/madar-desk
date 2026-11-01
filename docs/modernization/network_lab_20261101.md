# Madar Desk isolated multi-client network acceptance

## Verified topology

An actual Windows 10 Pro computer running Madar Desk source SHA
0efa0f25f2901b8e1ab9943a06c8b73fec4a2258 was used to launch
real native_app.Bridge and LanService instances.

~~~
   Real Madar HTTPS host / localhost ephemeral port
          |                 |                |
    Editor A PID       Editor B PID       Viewer C PID
    isolated data      isolated data      isolated data
~~~

Each real Python client runs in its own Windows process and isolated
APPDATA/LOCALAPPDATA profile with only synthetic customer data. The host
binds 127.0.0.1 only and uses a public TEST certificate with verified
fingerprint pinning. These are independent processes, not separate OS
virtual machines or physical devices.

## Test evidence

| Scenario | Result |
| --- | --- |
| Basic lab, host plus two actual Bridge subprocesses | 6/6 PASS on a separate direct rerun, evidence in tools/network_lab/evidence/last-run.json |
| Extended network lab, host plus three actual Bridge client subprocesses | 35/35 PASS in independent final rerun, evidence in tests/network_lab/evidence_latest.json |
| JavaScript LAN pairing, account UI, sync indicator, native bridge | 16/16 PASS |
| Python syntax compilation of lab files | PASS |
| Cross-OS Debian WSL2 to Windows HTTPS | BLOCKED: TLS request timed out, no HTTP response |

Tested actions include distinct synthetic roles and projects, login,
viewer write and editor admin-action denial, wrong TLS-pin rejection,
simultaneous editor edits (one accepted CAS write, one rejected),
offline queueing, safe nonoverlapping merge, preservation of same-card
conflicts, host restart, client restart and disk persistence.

The independently executed basic lab was cleaned up automatically after
the run. The extended lab likewise removes its disposable profiles.

## Cross-OS blocker and safety

Debian WSL2 guest was observed at 172.19.246.236 and Windows
vEthernet (WSL) gateway at 172.19.240.1. The real Madar LAN host
was started on the gateway address. Two TLS attempts from Debian
timed out with OpenSSL exit code 124 and zero response bytes.
One attempt used a temporary firewall rule restricted to the
WSL interface, guest IP and test port; that rule was subsequently
removed and a query showed no such rules. The cause of the
connectivity failure was not established.

Hyper-V-All was observed Disabled. No extra Windows OS virtual
machines, containers, permanent firewall changes, Windows Services
or physical LAN clients were created. The running user's installed
Madar Desk 1.0.2 and genuine accounting data were untouched.

## Re-run

~~~powershell
python tools/network_lab/lab.py run
python tests/network_lab/run_multi_client.py
node --test --test-concurrency=1 tests/madar_lan_pairing_ui_runtime.test.cjs tests/madar_lan_user_ui_runtime.test.cjs tests/sync_health.test.cjs tests/native_bridge_readiness.test.cjs
~~~

For detailed configuration, review tools/network_lab/README.md.
Successful synthetic API tests do not substitute for real Windows
Service deployment, two-PC networking, GUI end-to-end interaction,
or operational financial data migration acceptance.
