"""Command-line entry point for lifecycle operations and the adapter service."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional, Sequence

from dcc_mcp_core import capture_bootstrap_errors

from .__version__ import __version__
from .install import (
    MIN_CORE_VERSION,
    VERBS,
    bootstrap_log_dir,
    run,
    runtime_cli_from_receipt,
)
from .server import start_server, stop_server


def _print_report(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return
    print(f"DCC-MCP Premiere {report.get('verb')}: {report['status']}")
    verification = report.get("verify") or {}
    if verification.get("failure_reason"):
        print(f"Verification: {verification['failure_reason']}")
    for step in report.get("next_steps", []):
        print(f"Next: {step['description']}")


def _serve(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Start the DCC-MCP Premiere adapter")
    parser.add_argument("--port", type=int)
    parser.add_argument("--broker-url")
    options = parser.parse_args(list(argv))
    if not os.getenv("ADOBEPY_TOKEN"):
        print("ADOBEPY_TOKEN must be configured in the environment", file=sys.stderr)
        return 10
    if not os.getenv("ADOBEPY_BROKER_PATH"):
        runtime = runtime_cli_from_receipt()
        if runtime:
            os.environ["ADOBEPY_BROKER_PATH"] = runtime
    log_dir = bootstrap_log_dir()
    try:
        with capture_bootstrap_errors(
            "premiere",
            adapter_version=__version__,
            min_core_version=MIN_CORE_VERSION,
            phase="adapter-start",
            log_dir=str(log_dir),
        ):
            start_server(port=options.port, broker_url=options.broker_url)
        log_dir.mkdir(parents=True, exist_ok=True)
        marker = log_dir / "last-success.json"
        marker.write_text(
            json.dumps({"adapter_version": __version__, "status": "started"}) + "\n",
            encoding="utf-8",
        )
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        stop_server()


def main(argv: Optional[Sequence[str]] = None) -> int:
    resolved = list(sys.argv[1:] if argv is None else argv)
    if resolved and resolved[0] in {"-h", "--help"}:
        print("usage: dcc-mcp-premiere {install,status,verify,uninstall,upgrade,serve} [options]")
        return 0
    if resolved and resolved[0] == "serve":
        return _serve(resolved[1:])
    if not resolved:
        print(
            "A verb is required: install, status, verify, uninstall, upgrade, or serve",
            file=sys.stderr,
        )
        return 10
    if resolved[0] not in VERBS:
        print(f"Unknown verb: {resolved[0]}", file=sys.stderr)
        return 10
    report, code, as_json = run(resolved)
    _print_report(report, as_json)
    return code


__all__ = ["main"]
