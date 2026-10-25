# Madar Desk 1.0 — MCP read-only stdio adapter

## Implemented scope

`mcp_stdio_v1.py` is an **opt-in client-side MCP process**. The MCP host starts it as a subprocess and exchanges one UTF-8 JSON-RPC 2.0 object per newline over stdin/stdout. It **does not open a listening socket**. Every Madar operation calls the existing `GET /integrations/v1/*` endpoints on the **already running** HTTPS LAN server. No SQLite/JSON store, real APPDATA, finance, files, local commands, arbitrary URLs, HTTP listener, or write routes are accessed by the adapter.

The adapter implements the MCP legacy `initialize`, `notifications/initialized`, `ping`, `tools/list`, and `tools/call` methods. It negotiates protocol revisions `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`; for unknown requested versions it advertises `2025-11-25` so clients can explicitly accept/reject negotiation. Other methods return JSON-RPC `-32601`, and JSON-RPC notifications produce no response. No resources, prompts, subscriptions, sampling, elicitation, tasks, Streamable HTTP, or MCP OAuth flows are exposed. This is a bounded **legacy handshake-based subset**, not an assertion of full latest-spec compatibility.

**Compatibility note (October 2026):** MCP revision `2026-07-28` replaced `initialize/initialized` with stateless per-request metadata and `server/discover`. This adapter deliberately speaks the older MCP era and does not implement the 2026 wire format. Clients that support 2025-era stdio negotiation can use it; modern-only clients need a protocol adapter upgrade. Specification references: [2025 tools](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-06-18/server/tools.mdx), [2026 changes](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx).

## Three published MCP tools

| Tool | Arguments | Outbound HTTPS request | Result fields |
| --- | --- | --- | --- |
| `madar_list_projects` | `{}` | `GET /integrations/v1/projects` | `projects: [{id,name}]` |
| `madar_list_cards` | optional `projectId` (ASCII ID), `limit` (1–200, default 100) | `GET /integrations/v1/cards?limit=N[&projectId=ID]` | `revision`, `cards`, `hasMore` |
| `madar_get_card` | required `cardId` (ASCII ID) | `GET /integrations/v1/cards/ID` | `card` |

MCP `tools/call` returns a JSON-serialized payload inside a standard MCP `content: [{type:"text",text:"..."}]` array with `isError:false`. On API errors, the tool returns `isError:true` and a fixed safe error code such as `not_found`, `permission_denied`, `authentication_required`, `certificate_mismatch`, `integration_unavailable`, `response_too_large`. Invalid JSON-RPC method, params, tool name or argument fields return a JSON-RPC error. No upstream exception text or credentials are echoed.

The adapter re-allowlists fields even after consuming the HTTPS JSON response: card `id`, `projectId`, `title`, `status`, `priority`, `dueDate`; project `id`, `name`. Current LAN user grants and key expiry/revocation are enforced **by `IntegrationRouter` on every HTTPS request**. List-card API has no pagination cursor; `hasMore:true` is not a promise that remaining cards can be fetched with offsets.

## Admin setup and exact client configuration

1. Start Madar Desk as an HTTPS LAN host. Its integration router must be mounted at `/integrations/v1/` on **that HTTPS listener** (verified in the examined `lan.py`). The MCP adapter does not mount endpoints or start Madar automatically.
2. In the trusted Madar host admin workflow, issue a separate short-lived integration key for an existing, narrowly scoped account: `integrationIssueKey("account-name", ["read"], lifetime_seconds=600)` (60–86,400 seconds supported by host; prefer short TTL). Admin must provide the account’s intended project grants. Do not issue a write-capable key to this read-only client.
3. Obtain the TLS server leaf-certificate SHA-256 fingerprint from the trusted host interface or out-of-band administrative channel, never from the untrusted connection itself. For the local test certificate only, `lan.certificate_fingerprint(certfile)` computes this value.
4. Configure the MCP host to launch Python 3.12+ with a **full absolute path** to `mcp_stdio_v1.py` and pass three environment variables. Example MCP host configuration (replace placeholders with actual values from the running host):

```json
{
  "mcpServers": {
    "madar-readonly": {
      "command": "C:\\Path\\To\\Python312\\python.exe",
      "args": ["-u", "D:\\CoS-Test\\madar-desk\\mcp_stdio_v1.py"],
      "env": {
        "MADAR_MCP_URL": "https://127.0.0.1:48370",
        "MADAR_MCP_CERT_SHA256": "<64-hex-character-trusted-leaf-cert-SHA256>",
        "MADAR_MCP_INTEGRATION_KEY": "<short-lived-mdv1_-prefixed-secret>"
      }
    }
  }
}
```

`127.0.0.1` works only when the MCP host and Madar HTTPS host are on the **same computer**. For a different LAN computer use the server's *actual private IPv4/IPv6 address* and reachable HTTPS port. The URL must be an HTTPS **origin** using a private or loopback IP literal and explicit port; DNS hostnames, public IPs, URL paths, fragments, query strings, credentials in URLs, redirects, and plaintext HTTP are rejected. Replace integration keys after a Madar host restart: the host retains hashed keys in RAM only.

Environment variables can be visible to the parent MCP host and OS process inspection. Restrict access to the MCP host's configuration, avoid committing configuration files containing live secrets, and remove the secret when unused. Keys are never accepted as command-line arguments or stdin RPC parameters. The adapter emits no operational credentials to stdout/stderr; stdout is reserved for JSON-RPC.

## Bounded security contract

* Stdio **input line ≤65,536 bytes**, valid newline-terminated UTF-8 object, duplicate JSON names rejected; too-long/unterminated input is rejected and the process terminates to avoid unbounded drains. No JSON-RPC batches.
* TLS minimum 1.2, explicit 32-byte SHA-256 certificate digest pin checked **on the same connected socket before any integration header is sent**. No redirect following, HTTP fallback or external fetch parameters.
* Per-request HTTPS timeout 5 seconds, response body ≤262,144 bytes, complete stdio response ≤524,288 bytes. No file or subprocess operations after startup; outbound requests are limited to 3 fixed GET path families and never contain arbitrary client-supplied URL text.
* Up to **60 tool calls per rolling minute**, per stdio process (not a global/account-wide server quota); invalid input does not contact HTTPS. Project listing additionally requires a JSON array with at most 10,000 elements, card listing at most the requested limit.
* Invalid secrets, pins, URL or unavailable HTTPS host fail closed. Certificate pinning verifies peer identity against the trusted administrator-supplied certificate fingerprint; it does not provide certificate lifecycle management or PKI hostname validation. Do not treat a fingerprint copied from an untrusted machine as identity proof.
* MCP clients inherently receive the authorized project/card data. Only configure trusted MCP hosts, local account settings, and AI clients with access appropriate to the account grants.

## Verification

```powershell
py -3.12 -m unittest tests.test_mcp_stdio_v1 -v
```

Tests use temporary `APPDATA`/`LOCALAPPDATA` paths and a disposable `Bridge` plus a **real TLS loopback `LanService`** with the repository's public test-only TLS fixture. The suite checks a genuine spawned stdio subprocess, full initialization and tool discovery, project/card reads, field allowlists, hidden card behavior, key revocation, bad pin **before HTTP request dispatch**, malformed/oversized JSON-RPC, invalid methods/args, and insecure target rejection. This is limited to localhost and Python 3.12 test conditions; cross-machine LAN behavior, a physical Windows installer, third-party MCP client interoperability, and full modern 2026 MCP conformance require separate verification.

Observed in this worker's isolated workspace on Python 3.12.10: `py -3.12 -m unittest tests.test_mcp_stdio_v1 -v` **9/9 PASS** (13.038s). `py -3.12 -m compileall -q mcp_stdio_v1.py tests/test_mcp_stdio_v1.py` **PASS**. The worker did not run the full Python/npm suites or change the packaged Windows EXE; those are Prime's separate release gates.
