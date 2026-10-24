# Architecture

## Ownership boundaries

- `DccServerBase` owns MCP, REST readiness, instance discovery, jobs, and skill
  loading.
- `adobepy` owns the shared local broker, authenticated UXP bridge protocol,
  Premiere proxy objects, TickTime conversion, and UXP modal execution.
- `runtime.py` owns the adapter's required typed-method contract and real host
  version probe.
- `operations.py` owns validation, bounded traversal, allowlisted paths, output
  verification, and calls only the typed `adobe.premiere` facade.
- `tools.yaml` owns the public contract. Skill scripts only wrap operations in
  the standard DCC-MCP result envelope.
- Premiere and Adobe Media Encoder continue to own project semantics, codecs,
  preset behavior, licensing, and final encoding.

## Readiness sequence

1. The adapter ensures one shared `adobepy` broker using the configured URL and
   token.
2. It locates a connected `premiere` session for the configured target.
3. It compares the session's advertised namespaces and methods against
   `REQUIRED_METHODS`.
4. It performs a real typed `app.getVersion` RPC.
5. Only then does `dcc_ready` become true. A watchdog repeats the probe and
   withdraws readiness when the bridge or host disconnects.

MCP can remain available while Premiere is disconnected, allowing discovery
and diagnostics without falsely reporting the host ready.

## Security and resource limits

The public contract contains no raw JavaScript, `evalJs`, shell command,
arbitrary UXP method, or arbitrary output-extension entry point. Input,
output, and preset paths are resolved and checked against separate allowlists.
Existing outputs and parent creation require explicit opt-ins.

Project traversal, result pages, sequences, tracks, clips, selected items,
media imports, file sizes, aggregate input bytes, marker text, and frame pixels
all have explicit bounds. Synchronous save-as and frame exports must exist on
disk and return bytes plus SHA-256. AME jobs are reported as queued, never as
completed merely because Premiere accepted the job.

## Validation boundary

Unit tests use a contract-compatible fake of the typed `adobe.premiere` facade
to validate behavior on Python 3.9 and 3.12. They are not live-host proof.
`tools/live_premiere_smoke.py` is the acceptance path for an installed,
licensed Premiere host and deliberately uses typed DCC-MCP CLI calls rather
than importing adapter operations directly.
