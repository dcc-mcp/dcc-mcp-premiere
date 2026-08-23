# Install DCC-MCP Premiere

This runbook installs, verifies, upgrades, and removes the Premiere adapter through
the agent-first Install SOP v1 contract. The installer plans by default and does
not automate Adobe UXP Developer Tool or the Premiere UI.

## Requirements

- Adobe Premiere Pro 25.6 or newer with UXP support.
- Python 3.9 or newer containing `dcc-mcp-premiere` and
  `dcc-mcp-core>=0.19.45,<1.0.0`.
- `ADOBEPY_TOKEN` set in the environment. Reuse the same private local token for
  the broker and UXP plugin; it is never written to reports or receipts.
- Adobe UXP Developer Tool for the unsigned development-plugin loading step.
- User write access to the DCC-MCP data directory.

Windows x64 is the complete supported path. The installer acquires only the pinned
`adobepy` 0.6.2 runtime archive and verifies SHA-256
`9ef9abb5e034359f12e9ce248b0030e38d34c76df343eb2713f18036068719a7`.
macOS host discovery is supported, but adobepy 0.6.2 publishes no macOS runtime
bundle; set `DCC_MCP_PREMIERE_ADOBEPY` to an operator-installed compatible CLI.
Premiere and UXP are unavailable on Linux, so Linux fails preflight without writes.

## Supported versions

| Adapter | Core | Premiere Pro / UXP | Python | Platform |
|---|---|---|---|---|
| 0.5.x | >=0.19.45,<1.0.0 | >=25.6.0 / manifest v5 | >=3.9 | Windows x64 |
| 0.5.x | >=0.19.45,<1.0.0 | >=25.6.0 / manifest v5 | >=3.9 | macOS, operator-provided adobepy CLI |
| 0.5.x | >=0.19.45,<1.0.0 | unavailable | >=3.9 | Linux unsupported |

`--dcc-path` selects an exact Premiere executable or macOS `.app`. The installer
reads Windows version resources or `Info.plist`; it never launches the host to
guess its version. Interpreter selection is `--python`, then
`DCC_MCP_INSTALL_PYTHON`, then the interpreter running the installed console script.

## Agent quick path

Install the wheel, configure the token in the process environment, inspect the
non-mutating plan, and execute it:

```bash
python -m pip install "dcc-mcp-premiere>=0.5,<1"
dcc-mcp-premiere install --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json --dry-run
dcc-mcp-premiere install --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json --yes
```

The result uses schema version 1 and stable exits: `0` success/plan, `10`
preflight, `20` pinned-runtime acquisition, `30` transaction, `40`
verify-to-usable, and `50` a proven Windows lock requiring restart. A fresh
unsigned plugin normally returns exit `40` after the filesystem transaction and
one `load-uxp-plugin-and-verify` next step; it does not claim the host is ready.

## Manual path

The installer stages the configured Premiere UXP plugin under the reported
`plugin_path`, moves any receipted previous tree to a transaction backup, commits
the new tree and receipt, and restores both on commit failure. It never
delete-then-copies an existing plugin.

1. Run the JSON dry-run and inspect the host, profile, interpreter, versions,
   install state, receipt path, and planned steps.
2. Execute with `--yes`.
3. In Adobe UXP Developer Tool, choose **Add Plugin**, select the exact reported
   `plugin_path/manifest.json`, and load it into Premiere Pro 25.6 or newer.
4. Start the adapter in an environment containing the same `ADOBEPY_TOKEN`:

   ```bash
   dcc-mcp-premiere serve
   ```

5. In another terminal, run the verify command below.

The GUI step is a physical Adobe development-signing boundary. The installer
does not close dialogs, send input, manipulate UXP Developer Tool, or report a
development plugin as persistently signed/registered.

## Verify

```bash
dcc-mcp-premiere status --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json
dcc-mcp-premiere verify --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json
```

Verification checks receipt/path consistency and file digests, imports the exact
adapter version in the selected interpreter, rejects a newer captured bootstrap
error, requires a matching broker/UXP Premiere session, then calls Core
`wait_for_sidecar_ready` with the real read-only typed tool
`premiere_project__get_status`. Broker health alone is not direct usability.

## Upgrade

```bash
python -m pip install --upgrade "dcc-mcp-premiere>=0.5,<1"
dcc-mcp-premiere upgrade --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json --dry-run
dcc-mcp-premiere upgrade --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json --yes
```

Upgrade uses the same staged transaction and preserves the prior plugin and
receipt until the new receipt is durable. Use upgrade after rotating
`ADOBEPY_TOKEN` so the staged UXP configuration is regenerated without exposing
the token.

## Uninstall

```bash
dcc-mcp-premiere uninstall --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json --dry-run
dcc-mcp-premiere uninstall --dcc-path "/absolute/path/to/Premiere" --python "/absolute/path/to/python" --json --yes
python -m pip uninstall dcc-mcp-premiere
```

Uninstall consumes the receipt and removes only an exact receipted plugin tree
and an installer-owned adobepy runtime. It refuses an unreceipted or modified
tree, preserves the user's projects and Adobe profiles, and is idempotent after
successful removal. Remove the development plugin entry from UXP Developer Tool
manually if Adobe retains it in that application's local list.

## Troubleshooting

| Result | Diagnosis | Action |
|---|---|---|
| Exit `10`, `host` | Premiere missing, unreadable, or below 25.6 | Pass the exact executable or `.app` with `--dcc-path`. |
| Exit `10`, `python`/`core` | Wrong sidecar interpreter or incompatible package | Install the reported versions into the interpreter passed with `--python`. |
| Exit `10`, `token` | No operator token | Set `ADOBEPY_TOKEN`; never put it on the command line. |
| Exit `10`, `partial`/`receipt` | Unknown or modified plugin files | Inspect the reported tree; do not delete user-owned content. Repair from a trusted receipt. |
| Exit `20` | Pinned adobepy archive unavailable or wrong SHA-256 | Retry the same pinned release; do not scrape or substitute `latest`. |
| Exit `30` | Stage, commit, receipt, uninstall, or rollback failed | Preserve the JSON report and retry only after resolving its exact path failure. |
| Exit `40`, `import` | Adapter is absent or wrong version in the selected Python | Reinstall the wheel in that exact interpreter. |
| Exit `40`, `bootstrap` | Adapter startup failed before registration | Inspect the bounded bootstrap directory reported by status/verify. |
| Exit `40`, `uxp_session` | Broker has no matching Premiere UXP session | Load the reported manifest in UXP Developer Tool and confirm token/target match. |
| Exit `40`, `readiness` | Session exists but typed Premiere readiness failed | Keep `dcc-mcp-premiere serve` running, then retry verify. |
| Exit `50` | A receipted tree is actually locked on Windows | Save work, close the reported owner, and repeat the same command. |

Bootstrap failures are captured under the user DCC-MCP Premiere data directory
as bounded `dcc-mcp-premiere.<pid>.host-errors.log` files. A successful service
start writes `last-success.json`, so stale older errors do not make later verify
calls fail.

Catalog `instructions_url` should point to:

```text
https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-premiere/main/install.md
```
