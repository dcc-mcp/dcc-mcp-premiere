"""Symbol-level compatibility floor for the resolved ``dcc-mcp-core``.

A version bound in ``pyproject.toml`` is only as honest as the symbols this
adapter actually imports. A core can satisfy a ``>=`` bound and still predate
one of those symbols, and the failure then surfaces as an ``ImportError``
traceback out of ``dcc_mcp_premiere.cli`` rather than as an actionable message.
This module resolves the floor from the symbols themselves and stays importable
even when core is too old to provide any of them.
"""

from __future__ import annotations

import importlib
from typing import Any

from .install_contract import INSTALL_EXIT_PREFLIGHT

# Every core symbol this adapter imports, as ``(module, attribute)`` pairs.
# Guarding on modules alone is not enough: core shipped `deployment` from
# 0.20.20 but `deployment.validate_install_sop_report` only from 0.20.28, so a
# module-level check passes on cores that then fail at call time.
REQUIRED_CORE_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("dcc_mcp_core", "capture_bootstrap_errors"),
    ("dcc_mcp_core", "DccCapabilities"),
    ("dcc_mcp_core", "DccContextSnapshot"),
    ("dcc_mcp_core", "DccServerOptions"),
    ("dcc_mcp_core", "validate_skill"),
    ("dcc_mcp_core.install_lifecycle", "inspect_install_root"),
    ("dcc_mcp_core.install_lifecycle", "safe_remove_tree"),
    ("dcc_mcp_core.install_lifecycle", "wait_for_sidecar_ready"),
    ("dcc_mcp_core.readiness", "AdapterReadinessBinder"),
    ("dcc_mcp_core.server_base", "DccServerBase"),
    ("dcc_mcp_core.skill", "skill_entry"),
)

# Lowest core release that publishes every symbol above *and* the `-v2` Install
# SOP schema artifact this adapter pins in `install_contract`. Measured by
# installing each release and importing the symbols, not inferred from a
# changelog: `capture_bootstrap_errors` appears in 0.19.90, `deployment` in
# 0.20.20, `deployment.validate_install_sop_report` in 0.20.28, and the `-v2`
# artifact in 0.20.34. Move this with the symbols, never ahead of them.
MIN_CORE_VERSION = "0.20.34"


class CoreTooOld(RuntimeError):
    """The resolved ``dcc-mcp-core`` predates a symbol this adapter imports."""

    exit_code = INSTALL_EXIT_PREFLIGHT

    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            "dcc-mcp-core is too old for dcc-mcp-premiere: missing "
            + ", ".join(missing)
            + f". Install dcc-mcp-core>={MIN_CORE_VERSION}."
        )
        self.missing = missing


def missing_core_symbols() -> list[str]:
    """Return the ``module.attribute`` names the resolved core does not provide."""
    missing: list[str] = []
    modules: dict[str, Any] = {}
    for module_name, attribute in REQUIRED_CORE_SYMBOLS:
        if module_name not in modules:
            try:
                modules[module_name] = importlib.import_module(module_name)
            except ImportError:
                modules[module_name] = None
        module = modules[module_name]
        if module is None or not hasattr(module, attribute):
            missing.append(f"{module_name}.{attribute}")
    return missing


def require_core_symbols() -> None:
    """Raise `CoreTooOld` when the resolved core predates a required symbol."""
    missing = missing_core_symbols()
    if missing:
        raise CoreTooOld(missing)


__all__ = [
    "MIN_CORE_VERSION",
    "REQUIRED_CORE_SYMBOLS",
    "CoreTooOld",
    "missing_core_symbols",
    "require_core_symbols",
]
