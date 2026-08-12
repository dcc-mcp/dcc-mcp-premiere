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
