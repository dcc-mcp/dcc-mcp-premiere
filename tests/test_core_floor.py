"""The declared core floor has to match the symbols this adapter imports.

`dcc-mcp-core>=0.19.45` was declared while `cli.py` already needed
`capture_bootstrap_errors`, which core only ships from 0.19.90: the bound
admitted combinations that fail at import time. These tests pin the bound to the
symbols so the two cannot drift apart again.
"""

import re
from pathlib import Path

import pytest

from dcc_mcp_premiere import cli, core_compat
from dcc_mcp_premiere import install as installer

ROOT = Path(__file__).resolve().parents[1]

# Lowest core release that provides each item, measured by installing releases
# and importing the symbols -- not read off the changelog. Re-measure before
# changing them.
MEASURED_FLOORS: dict[str, tuple[int, ...]] = {
    "dcc_mcp_core.capture_bootstrap_errors": (0, 19, 90),
    "dcc_mcp_core.deployment": (0, 20, 20),
    "dcc_mcp_core.deployment.validate_install_sop_report": (0, 20, 28),
    "adapter-install-sop-v2.schema.json artifact": (0, 20, 34),
}

_BOUND = re.compile(r'dcc-mcp-core>=\s*([0-9][^",<]*)')


def _declared_core_floor() -> str:
    """The `dcc-mcp-core` lower bound declared in pyproject.toml."""
    match = _BOUND.search((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert match is not None, "pyproject.toml declares no dcc-mcp-core lower bound"
    return match.group(1).strip()


def _floor_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def test_declared_floor_is_the_single_source_of_truth():
    # The bound pip enforces, the preflight message, and the symbol guard must
    # name the same release; a stale copy of the constant reintroduces the bug.
    declared = _declared_core_floor()

    assert declared == core_compat.MIN_CORE_VERSION
    assert installer.MIN_CORE_VERSION == core_compat.MIN_CORE_VERSION


def test_declared_floor_covers_every_measured_symbol_floor():
    declared = _floor_tuple(_declared_core_floor())

    for name, floor in MEASURED_FLOORS.items():
        assert declared >= floor, f"{name} needs core >={'.'.join(map(str, floor))}"


def test_core_floor_tool_reads_the_declared_bound():
    # Loaded by path because `tools/` is not on the import path.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "install_core_floor", ROOT / "tools" / "install_core_floor.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.declared_core_floor() == core_compat.MIN_CORE_VERSION


def test_resolved_core_exports_every_required_symbol():
    # Guards on modules rather than symbols pass on cores that then fail at call
    # time, so require the symbols themselves.
    assert core_compat.missing_core_symbols() == []


def test_require_core_symbols_raises_an_actionable_error(monkeypatch):
    monkeypatch.setattr(
        core_compat,
        "missing_core_symbols",
        lambda: ["dcc_mcp_core.capture_bootstrap_errors"],
    )

    with pytest.raises(core_compat.CoreTooOld) as excinfo:
        core_compat.require_core_symbols()

    message = str(excinfo.value)
    assert "capture_bootstrap_errors" in message
    assert f"dcc-mcp-core>={core_compat.MIN_CORE_VERSION}" in message
    assert excinfo.value.missing == ["dcc_mcp_core.capture_bootstrap_errors"]


def test_cli_missing_symbols_fail_preflight_instead_of_import_error(monkeypatch, capsys):
    # The point of the guard: an old core yields a named preflight failure with a
    # remediation, not a traceback out of the import block.
    def boom():
        raise core_compat.CoreTooOld(["dcc_mcp_core.capture_bootstrap_errors"])

    monkeypatch.setattr(cli, "require_core_symbols", boom)

    assert cli.main(["status"]) == core_compat.CoreTooOld([]).exit_code

    stderr = capsys.readouterr().err
    assert "capture_bootstrap_errors" in stderr
    assert f"dcc-mcp-core>={core_compat.MIN_CORE_VERSION}" in stderr
