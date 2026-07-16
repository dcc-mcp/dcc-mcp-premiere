# dcc-mcp-premiere

MCP adapter for Adobe Premiere Pro, built on the shared `adobepy` broker, UXP bridge, and typed facade.

```bash
pip install dcc-mcp-premiere
```

Install the shared bridge with `adobepy install-bridge premiere --dest <plugin-dir> --token <token>`, load it with Adobe UXP Developer Tool in Premiere Pro 25.6 or later, then start the adapter. Each adapter instance uses an OS-assigned port and registers it for CLI discovery. Connect through the stable gateway at `http://127.0.0.1:9765/mcp`; set `DCC_MCP_PREMIERE_PORT` only when a fixed direct endpoint is required.

Set `ADOBEPY_TOKEN` to the same non-default token used when installing the bridge.

## Tools

- `premiere-project.inspect_project`
- `premiere-project.list_sequences`
- `premiere-project.save_project`
