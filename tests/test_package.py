import json
from pathlib import Path
from types import SimpleNamespace

from dcc_mcp_premiere import __version__


def test_version_metadata_is_synchronized():
    root = Path(__file__).parents[1]
    assert f'version = "{__version__}"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    manifest = json.loads((root / ".release-please-manifest.json").read_text(encoding="utf-8"))
    assert manifest["."] == __version__


def test_adapter_uses_current_shared_adobepy_runtime():
    root = Path(__file__).parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"adobepy>=0.6.2,<1.0.0"' in pyproject
    assert not (root / "src" / "dcc_mcp_premiere" / "bridge.py").exists()


def test_install_sop_entrypoint_docs_and_payload_are_shipped():
    root = Path(__file__).parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dcc-mcp-premiere = "dcc_mcp_premiere.cli:main"' in pyproject

    package = root / "src" / "dcc_mcp_premiere"
    for filename in ("__main__.py", "cli.py", "install.py", "install_contract.py"):
        assert (package / filename).is_file()

    runbook = (root / "install.md").read_text(encoding="utf-8")
    for heading in (
        "## Requirements",
        "## Supported versions",
        "## Agent quick path",
        "## Manual path",
        "## Verify",
        "## Upgrade",
        "## Uninstall",
        "## Troubleshooting",
    ):
        assert heading in runbook
    assert "https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-premiere/main/install.md" in runbook


def test_install_sop_contract_matches_the_pending_core_foundation():
    from dcc_mcp_premiere.install_contract import INSTALL_EXIT_CODES, load_install_sop_schema

    assert INSTALL_EXIT_CODES == {
        "ok": 0,
        "preflight": 10,
        "acquire": 20,
        "install": 30,
        "verify": 40,
        "requires_restart": 50,
    }
    schema = load_install_sop_schema()
    assert schema["properties"]["schema_version"] == {"const": 1, "type": "integer"}
    assert set(schema["required"]) >= {
        "schema_version",
        "status",
        "dcc_type",
        "adapter_version",
        "core_version",
        "steps",
        "next_steps",
        "receipt_path",
        "verify",
    }


def test_start_server_defers_port_resolution_to_core(monkeypatch):
    from dcc_mcp_premiere import server as server_module

    ports = []
    stub = SimpleNamespace(
        is_running=False,
        run_registration=lambda **_kwargs: None,
        start=lambda: None,
        stop=lambda: None,
    )

    monkeypatch.setattr(server_module, "_server", None)
    monkeypatch.setattr(
        server_module,
        "PremiereMcpServer",
        lambda port=None, **_kwargs: ports.append(port) or stub,
    )
    monkeypatch.setenv("DCC_MCP_PREMIERE_PORT", "8765")

    server_module.start_server(0)
    server_module.stop_server()
    server_module.start_server()
    server_module.stop_server()

    assert ports == [0, None]
