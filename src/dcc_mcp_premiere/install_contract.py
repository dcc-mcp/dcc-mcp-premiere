"""Install SOP contract surface, resolved from the installed dcc-mcp-core."""

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
        load_install_sop_schema,
    )
except ImportError:
    # Only reached when the resolved core has no Install SOP deployment module.
    # Reports still have to be well formed then, so the fallback keeps both
    # counters at their published values.
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


def _install_sop_artifact_revision() -> int:
    """Return the revision of the published Install SOP schema *artifact*.

    Core renamed ``INSTALL_SOP_SCHEMA_VERSION`` to ``INSTALL_SOP_SCHEMA_REVISION``:
    the old name read like the report document's ``schema_version`` field while it
    carried the artifact revision, and several adapters emitted the artifact
    revision into a report. The old name survives one release cycle as a
    deprecated alias that warns on access, so resolve the new name first and only
    fall back to the old one when the resolved core predates the rename.
    """
    try:
        from dcc_mcp_core import deployment
    except ImportError:
        return 1

    for name in ("INSTALL_SOP_SCHEMA_REVISION", "INSTALL_SOP_SCHEMA_VERSION"):
        revision = getattr(deployment, name, None)
        if revision is not None:
            return revision
    return 1


# Revision of the published Install SOP schema *artifact*
# (`adapter-install-sop-vN.schema.json`), 2 since dcc-mcp-core 0.20.36. It is NOT
# the value of the `schema_version` field that the artifact pins on a report
# document: that field is a separate, stable counter declared as
# `properties.schema_version.const` and stays at 1, because artifact revisions
# only add optional members. The two are named separately here -- conflating them
# makes every status/verify/install report fail validation the moment the
# resolved core advances.
INSTALL_SOP_SCHEMA_REVISION = _install_sop_artifact_revision()

# Adapter-local name for the same counter, kept because report payloads refer to
# the artifact revision under this name.
ARTIFACT_SCHEMA_VERSION = INSTALL_SOP_SCHEMA_REVISION

# Identity of the artifact the adapter validates against. Core 0.20.30 rewrote
# `adapter-install-sop-v1.schema.json` in place -- same filename and `$id`,
# different bytes -- so `-v1` is frozen at the 0.20.30 bytes and every content
# change now ships as the next revision. The adapter does not vendor a copy of
# this core-owned contract: it reads the artifact core packages (core verifies the
# bytes it loads) and pins which artifact that must be here, so a core that ships
# a new revision fails tests instead of an end-user install. Moving to a newer
# revision is a deliberate migration, never a silent one.
INSTALL_SOP_SCHEMA_ID = "https://dcc-mcp.github.io/schemas/adapter-install-sop-v2.schema.json"
INSTALL_SOP_SCHEMA_SHA256 = "daa5840e07c956d7c9269e5709d6993a3988b905f986c06e7c4c02f5023e9422"

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
    "INSTALL_SOP_SCHEMA_ID",
    "INSTALL_SOP_SCHEMA_REVISION",
    "INSTALL_SOP_SCHEMA_SHA256",
    "SCHEMA_VERSION",
    "load_install_sop_schema",
]
