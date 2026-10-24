"""Install the exact ``dcc-mcp-core`` floor declared in ``pyproject.toml``.

CI uses this to exercise the declared lower bound instead of always resolving the
latest release. Reading the bound from ``pyproject.toml`` keeps the matrix arm
honest: the floor under test is always the floor the package declares.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

_BOUND = re.compile(r'dcc-mcp-core>=\s*([0-9][^",<]*)')


def declared_core_floor() -> str:
    """Return the ``dcc-mcp-core`` lower bound declared in pyproject.toml."""
    match = _BOUND.search(PYPROJECT.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit("no dcc-mcp-core lower bound found in pyproject.toml")
    return match.group(1).strip()


def main() -> int:
    floor = declared_core_floor()
    print(f"installing declared dcc-mcp-core floor: {floor}")
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", f"dcc-mcp-core=={floor}"]
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
