# dcc-mcp-premiere

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/dcc-mcp-premiere-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/dcc-mcp-premiere.svg">
    <img src="docs/assets/dcc-mcp-premiere.svg" alt="DCC-MCP · PREMIERE PRO" width="600">
  </picture>
</p>

Typed DCC-MCP control for Adobe Premiere Pro through the shared `adobepy`
broker and Adobe's UXP runtime. The adapter exposes bounded project, media,
timeline, marker, save, frame-export, and AME queue operations. It deliberately
does not expose raw JavaScript, `evalJs`, shell commands, or arbitrary UXP calls.

![Premiere Pro typed project and timeline workflow](docs/images/premiere-showcase.webp)

_Illustrative workflow generated with OpenAI ImageGen from the retained source in `docs/images/sources`; it is not a Premiere Pro screenshot or host-validation artifact._

## Install

```bash
python -m pip install dcc-mcp-premiere
adobepy install-bridge premiere --dest <plugin-dir> --token <non-default-token>
```

Load the generated bridge with Adobe UXP Developer Tool in Premiere Pro 25.6
or later. Set `ADOBEPY_TOKEN` to the same token, start the adapter, then verify
the connected host through DCC-MCP discovery:

```bash
dcc-mcp-cli wait-ready --dcc-type premiere --timeout-secs 60
dcc-mcp-cli load-skill premiere-project --dcc-type premiere
```

Each adapter instance uses an OS-assigned port and registers with DCC-MCP
discovery. Agents should connect through the stable local gateway at
`http://127.0.0.1:9765/mcp`. Set `DCC_MCP_PREMIERE_PORT` only for a deliberately
fixed direct endpoint.

## Typed tools

Inspection:

- `get_status`
- `inspect_project`
- `list_sequences`
- `inspect_sequence`
- `list_project_items`
- `list_selected_clips`
- `list_encoder_presets`

Project and timeline authoring:

- `create_bin`
- `import_media`
- `create_sequence`
- `insert_project_item`
- `overwrite_project_item`
- `create_marker`

Persistence and export:

- `save_project`
- `save_project_as`
- `queue_sequence_export`
- `export_frame`

List and scan operations are paginated and bounded. Imports accept at most 100
files, with per-file and aggregate byte limits. Track indices, marker text,
frame dimensions, and output extensions are validated before invoking the host.
AME export reports `queued=true`; completion must be verified separately.

## Safe local paths

The adapter resolves paths before calling Premiere and confines them to:

- `DCC_MCP_PREMIERE_ALLOWED_INPUT_ROOTS` for imported media
- `DCC_MCP_PREMIERE_ALLOWED_OUTPUT_ROOTS` for `.prproj` and exported media
- `DCC_MCP_PREMIERE_ALLOWED_PRESET_ROOTS` for `.sqpreset` and `.epr` files

Each variable uses the platform path separator and defaults to the current
user's home directory. Existing outputs require `overwrite=true`; missing
parent directories require `create_parents=true`. Verified synchronous outputs
include byte count and SHA-256.

## Real-host acceptance

Automated tests use contract-compatible facade fakes; they are not represented
as live Premiere proof. With a disposable project open and the UXP bridge
connected, configure the three allowlists and run:

```bash
set DCC_MCP_PREMIERE_SMOKE_MEDIA=C:\path\to\media.mp4
set DCC_MCP_PREMIERE_SMOKE_ROOT=C:\path\to\writable-evidence
python tools/live_premiere_smoke.py
```

The smoke script uses `dcc-mcp-cli` for readiness, skill loading, and every
typed call. It imports media, authors and inspects a sequence, adds a marker,
saves a verified project copy, exports a verified frame, and prints hashes.
Set `DCC_MCP_PREMIERE_SMOKE_EPR` to an allowlisted `.epr` file to include an AME
queue test.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python tools/lint_skills.py
python -m build
python -m twine check dist/*
```

See `docs/architecture.md` for ownership, readiness, and security boundaries.
