"""Install SOP v1 compatibility imports while Core #2320 is pending."""

from __future__ import annotations

try:
    from dcc_mcp_core.deployment import (
        INSTALL_EXIT_ACQUIRE,
        INSTALL_EXIT_CODES,
        INSTALL_EXIT_INSTALL,
        INSTALL_EXIT_OK,
        INSTALL_EXIT_PREFLIGHT,
        INSTALL_EXIT_REQUIRES_RESTART,
        INSTALL_EXIT_VERIFY,
        INSTALL_SOP_SCHEMA_VERSION,
        load_install_sop_schema,
    )
except ImportError:
    INSTALL_SOP_SCHEMA_VERSION = 1
    INSTALL_EXIT_OK = 0
    INSTALL_EXIT_PREFLIGHT = 10
    INSTALL_EXIT_ACQUIRE = 20
    INSTALL_EXIT_INSTALL = 30
    INSTALL_EXIT_VERIFY = 40
    INSTALL_EXIT_REQUIRES_RESTART = 50
    INSTALL_EXIT_CODES = {
        "ok": INSTALL_EXIT_OK,
        "preflight": INSTALL_EXIT_PREFLIGHT,
        "acquire": INSTALL_EXIT_ACQUIRE,
        "install": INSTALL_EXIT_INSTALL,
        "verify": INSTALL_EXIT_VERIFY,
        "requires_restart": INSTALL_EXIT_REQUIRES_RESTART,
    }

    def load_install_sop_schema():
        """Return the foundation schema shape without requiring unreleased Core."""
        return {
            "properties": {"schema_version": {"const": 1, "type": "integer"}},
            "required": [
                "schema_version",
                "status",
                "dcc_type",
                "adapter_version",
                "core_version",
                "steps",
                "next_steps",
                "receipt_path",
                "verify",
            ],
        }


__all__ = [
    "INSTALL_EXIT_ACQUIRE",
    "INSTALL_EXIT_CODES",
    "INSTALL_EXIT_INSTALL",
    "INSTALL_EXIT_OK",
    "INSTALL_EXIT_PREFLIGHT",
    "INSTALL_EXIT_REQUIRES_RESTART",
    "INSTALL_EXIT_VERIFY",
    "INSTALL_SOP_SCHEMA_VERSION",
    "load_install_sop_schema",
]
