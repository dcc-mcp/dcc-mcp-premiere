"""Exercise the production typed tool chain against an open Premiere host."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional


def run_cli(*args: str) -> Any:
    command = [
        "dcc-mcp-cli",
        "--gateway",
        "local",
        "--output",
        "json",
        "--non-interactive",
        *args,
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Command failed: %s\nstdout=%s\nstderr=%s"
            % (" ".join(command), completed.stdout, completed.stderr)
        )
    return json.loads(completed.stdout)


def call(name: str, arguments: Optional[dict[str, Any]] = None) -> Any:
    return run_cli(
        "call",
        f"premiere-project.{name}",
        "--dcc-type",
        "premiere",
        "--json",
        json.dumps(arguments or {}, separators=(",", ":")),
        "--wait",
        "--wait-timeout-secs",
        "300",
    )


def payload(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") or {}
    if result.get("isError"):
        raise RuntimeError(f"Typed call returned an error: {result}")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError(f"Typed call returned no structured content: {response}")
    return structured


def required_file(name: str, extensions: set[str]) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must name an existing file")
    path = Path(value).expanduser().resolve()
    if not path.is_file() or (extensions and path.suffix.lower() not in extensions):
        raise RuntimeError(f"{name} must name an existing {sorted(extensions)} file")
    return path


def main() -> None:
    media = required_file("DCC_MCP_PREMIERE_SMOKE_MEDIA", set())
    root_value = os.environ.get("DCC_MCP_PREMIERE_SMOKE_ROOT")
    if not root_value:
        raise RuntimeError("DCC_MCP_PREMIERE_SMOKE_ROOT must name an existing writable directory")
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError("DCC_MCP_PREMIERE_SMOKE_ROOT must name an existing directory")

    run_cli("wait-ready", "--dcc-type", "premiere", "--timeout-secs", "60")
    run_cli("load-skill", "premiere-project", "--dcc-type", "premiere")

    suffix = str(int(time.time()))[-8:]
    bin_name = f"DCCMCP_{suffix}"
    sequence_name = f"DCCMCP_Sequence_{suffix}"
    project_path = root / f"dcc-mcp-premiere-live-{suffix}.prproj"
    frame_path = root / f"dcc-mcp-premiere-live-{suffix}.png"

    call("get_status")
    call("inspect_project")
    created_bin = payload(call("create_bin", {"name": bin_name}))
    bin_id = created_bin["bin"]["id"]
    imported = payload(call("import_media", {"paths": [str(media)], "target_bin": bin_id}))
    item_id = imported["items"][0]["id"]
    created_sequence = payload(call("create_sequence", {"name": sequence_name}))
    sequence_id = created_sequence["sequence"]["id"]
    call(
        "insert_project_item",
        {"project_item": item_id, "sequence": sequence_id, "time": 0},
    )
    call(
        "create_marker",
        {"name": "DCC-MCP live smoke", "sequence": sequence_id, "start": 0},
    )
    call("inspect_sequence", {"sequence": sequence_id, "include_clips": True})
    saved = payload(call("save_project_as", {"path": str(project_path)}))
    frame = payload(
        call(
            "export_frame",
            {"output_path": str(frame_path), "time": 0, "sequence": sequence_id},
        )
    )

    summary = {
        "typed_tools_exercised": 10,
        "bin": bin_name,
        "sequence": sequence_name,
        "project": saved["file"],
        "frame": frame["file"],
    }
    epr_value = os.environ.get("DCC_MCP_PREMIERE_SMOKE_EPR")
    if epr_value:
        preset = required_file("DCC_MCP_PREMIERE_SMOKE_EPR", {".epr"})
        queued = payload(
            call(
                "queue_sequence_export",
                {
                    "output_path": str(root / f"dcc-mcp-premiere-live-{suffix}.mp4"),
                    "preset_path": str(preset),
                    "sequence": sequence_id,
                },
            )
        )
        summary["ame_job"] = queued["job"]
        summary["typed_tools_exercised"] += 1
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
