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
    # Only reached when the resolved core has no Install SOP deployment module.
    # Reports still have to be well formed then, so the fallback keeps both
    # counters at their published values.
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


# `INSTALL_SOP_SCHEMA_VERSION` is the revision of the published Install SOP
# schema *artifact* (`adapter-install-sop-vN.schema.json`), 2 since
# dcc-mcp-core 0.20.36. It is NOT the value of the `schema_version` field that
# the artifact pins on a report document: that field is a separate, stable
# counter declared as `properties.schema_version.const` and stays at 1, because
# artifact revisions only add optional members. The two are named separately
# here -- conflating them makes every status/verify/install report fail
# validation the moment the resolved core advances.
ARTIFACT_SCHEMA_VERSION = INSTALL_SOP_SCHEMA_VERSION

# Value of the report document's own `schema_version` field. Kept in sync with
# `load_install_sop_schema()["properties"]["schema_version"]["const"]` by
# tests/test_install_lifecycle.py, which fails when the resolved core drifts.
SCHEMA_VERSION = 1


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "INSTALL_EXIT_ACQUIRE",
    "INSTALL_EXIT_CODES",
    "INSTALL_EXIT_INSTALL",
    "INSTALL_EXIT_OK",
    "INSTALL_EXIT_PREFLIGHT",
    "INSTALL_EXIT_REQUIRES_RESTART",
    "INSTALL_EXIT_VERIFY",
    "INSTALL_SOP_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "load_install_sop_schema",
]
