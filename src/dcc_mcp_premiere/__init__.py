"""Adobe Premiere Pro MCP adapter."""

from .__version__ import __version__
from .server import PremiereMcpServer

__all__ = ["PremiereMcpServer", "__version__"]
