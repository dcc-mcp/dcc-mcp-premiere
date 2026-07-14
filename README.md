# dcc-mcp-premiere

MCP adapter for Adobe Premiere Pro. It uses a bundled UXP panel as a typed, localhost-only bridge to Premiere's project APIs.

```bash
pip install dcc-mcp-premiere
```

Load the installed `dcc_mcp_premiere/premiere_uxp` folder with Adobe UXP Developer Tool in Premiere Pro 25.6 or later. The MCP endpoint defaults to `http://127.0.0.1:8765/mcp`.

Set the same non-default `DCC_MCP_PREMIERE_BRIDGE_TOKEN` in the adapter environment and the UXP panel before production use.

## Tools

- `premiere-project.inspect_project`
- `premiere-project.list_sequences`
- `premiere-project.save_project`
