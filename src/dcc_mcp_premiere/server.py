"""Premiere Pro MCP server lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dcc_mcp_core import DccServerOptions
from dcc_mcp_core.server_base import DccServerBase

from .__version__ import __version__
from .bridge import BridgeBroker

DEFAULT_PORT = 8765
_server: Optional["PremiereMcpServer"] = None


class PremiereMcpServer(DccServerBase):
    """MCP server whose typed calls are completed by the UXP panel."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self.bridge = BridgeBroker("DCC_MCP_PREMIERE", 47393)
        options = DccServerOptions.from_env(
            "premiere",
            Path(__file__).resolve().parent / "skills",
            port=port,
            server_name="dcc-mcp-premiere",
            server_version=__version__,
        )
        super().__init__(options=options)

    def start(self, **kwargs):
        self.bridge.start()
        return super().start(**kwargs)

    def stop(self) -> None:
        super().stop()
        self.bridge.stop()


def start_server(port: Optional[int] = None) -> PremiereMcpServer:
    global _server
    if _server is None or not _server.is_running:
        _server = PremiereMcpServer(
            port or int(os.environ.get("DCC_MCP_PREMIERE_PORT", DEFAULT_PORT))
        )
        _server.register_builtin_actions()
        _server.start()
    return _server


def stop_server() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None
