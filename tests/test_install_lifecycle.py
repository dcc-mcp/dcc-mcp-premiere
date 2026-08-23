import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dcc_mcp_premiere import install as installer
from dcc_mcp_premiere.runtime import PremiereStatus

ROOT = Path(__file__).resolve().parents[1]


def _prepare_lifecycle(tmp_path, monkeypatch):
    install_root = tmp_path / "install-root"
    host = tmp_path / "Adobe Premiere Pro.exe"
    host.write_bytes(b"premiere")
    adobepy = tmp_path / "adobepy.exe"
    adobepy.write_bytes(b"runtime")
    monkeypatch.setenv("DCC_MCP_PREMIERE_INSTALL_ROOT", str(install_root))
    monkeypatch.setenv("DCC_MCP_PREMIERE_ADOBEPY", str(adobepy))
    monkeypatch.setenv("ADOBEPY_TOKEN", "test-token-that-must-never-be-reported")
    monkeypatch.setattr(
        installer,
        "resolve_host",
        lambda _value: installer.HostInstall(
            host,
            "25.6.0",
            tmp_path / "profile" / "25.0",
            "flag",
        ),
    )
    monkeypatch.setattr(
        installer,
        "_target_versions",
        lambda _python: {"python": "3.12.0", "core": "0.19.91", "adapter": "0.5.0"},
    )

    def build_bridge(_cli, destination):
        (destination / "dist").mkdir(parents=True)
        (destination / "manifest.json").write_text(
            '{"host":{"app":"PR","minVersion":"25.6.0"}}',
            encoding="utf-8",
        )
        (destination / "dist" / "main.js").write_text("bridge", encoding="utf-8")
        (destination / "adobepy.config.js").write_text(
            "token=test-token-that-must-never-be-reported",
            encoding="utf-8",
        )

    monkeypatch.setattr(installer, "_build_bridge", build_bridge)
    return install_root, host


def test_module_entrypoint_reports_preflight_as_install_sop_json(tmp_path):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    missing_host = tmp_path / "Adobe Premiere Pro.exe"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "dcc_mcp_premiere",
            "status",
            "--json",
            "--dcc-path",
            str(missing_host),
            "--python",
            sys.executable,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 10
    result = json.loads(completed.stdout)
    assert result["schema_version"] == 1
    assert result["status"] == "failed"
    assert result["dcc_type"] == "premiere"
    assert result["verify"]["directly_usable"] is False
    assert result["verify"]["failure_stage"] == "host"
    assert result["next_steps"][0]["command"][:3] == [
        "dcc-mcp-premiere",
        "status",
        "--dcc-path",
    ]


def test_console_script_exposes_the_standard_lifecycle_surface():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'dcc-mcp-premiere = "dcc_mcp_premiere.cli:main"' in pyproject


def test_module_entrypoint_help_lists_the_lifecycle_without_error():
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")

    completed = subprocess.run(
        [sys.executable, "-m", "dcc_mcp_premiere", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0
    for verb in ("install", "status", "verify", "uninstall", "upgrade", "serve"):
        assert verb in completed.stdout


def test_install_dry_run_is_non_mutating_and_reports_complete_plan(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)

    report, code, as_json = installer.run(
        [
            "install",
            "--dcc-path",
            str(host),
            "--python",
            sys.executable,
            "--json",
            "--dry-run",
        ]
    )

    assert code == 0
    assert as_json is True
    assert report["schema_version"] == 1
    assert report["status"] == "planned"
    assert report["installation_state"] == "fresh"
    assert report["premiere_version"] == "25.6.0"
    assert report["uxp_manifest_version"] == 5
    assert report["uxp_min_version"] == "25.6.0"
    assert report["adobepy_runtime_version"] == "0.6.2"
    assert report["token_configured"] is True
    assert report["next_steps"][0]["command"][-2:] == ["--json", "--yes"]
    assert not install_root.exists()


def test_install_status_uninstall_receipt_round_trip(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]

    installed, install_code, _ = installer.run(["install", *common, "--yes"])
    status, status_code, _ = installer.run(["status", *common])
    removed, remove_code, _ = installer.run(["uninstall", *common, "--yes"])
    absent, absent_code, _ = installer.run(["uninstall", *common, "--yes"])

    assert install_code == status_code == remove_code == absent_code == 0
    assert installed["verify"]["directly_usable"] is True
    assert status["installation_state"] == "current"
    assert removed["status"] == absent["status"] == "ok"
    assert not installer.plugin_path(install_root).exists()
    assert not installer.receipt_path(install_root).exists()


def test_receipt_failure_restores_previous_plugin_and_receipt(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]
    _, code, _ = installer.run(["install", *common, "--yes"])
    assert code == 0
    marker = installer.plugin_path(install_root) / "previous.txt"
    marker.write_text("keep me", encoding="utf-8")
    old_receipt = installer.receipt_path(install_root).read_bytes()

    def reject_receipt(*_args):
        raise OSError("receipt write failed")

    monkeypatch.setattr(installer, "_write_json_atomic", reject_receipt)
    report, failed_code, _ = installer.run(["upgrade", *common, "--yes"])

    assert failed_code == 30
    assert report["verify"]["failure_stage"] == "install"
    assert marker.read_text(encoding="utf-8") == "keep me"
    assert installer.receipt_path(install_root).read_bytes() == old_receipt


def test_install_repairs_a_receipted_missing_plugin_tree(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]
    _, install_code, _ = installer.run(["install", *common, "--yes"])
    assert install_code == 0
    removed = installer.safe_remove_tree(installer.plugin_path(install_root))
    assert removed["success"] is True

    planned, plan_code, _ = installer.run(["install", *common, "--dry-run"])
    repaired, repair_code, _ = installer.run(["install", *common, "--yes"])

    assert plan_code == repair_code == 0
    assert planned["installation_state"] == "repair"
    assert repaired["steps"][-1]["previous_state"] == "repair"
    assert installer.plugin_path(install_root).is_dir()


def test_failed_stage_commit_restores_previous_plugin_and_receipt(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]
    _, code, _ = installer.run(["install", *common, "--yes"])
    assert code == 0
    marker = installer.plugin_path(install_root) / "previous.txt"
    marker.write_text("keep me", encoding="utf-8")
    old_receipt = installer.receipt_path(install_root).read_bytes()
    real_replace = installer.os.replace

    def reject_stage(source, destination):
        source_path = Path(source)
        if source_path.name == "uxp-plugin" and Path(destination) == installer.plugin_path(
            install_root
        ):
            raise OSError("stage commit failed")
        return real_replace(source, destination)

    monkeypatch.setattr(installer.os, "replace", reject_stage)
    report, failed_code, _ = installer.run(["upgrade", *common, "--yes"])

    assert failed_code == 30
    assert report["verify"]["failure_stage"] == "install"
    assert marker.read_text(encoding="utf-8") == "keep me"
    assert installer.receipt_path(install_root).read_bytes() == old_receipt


def test_install_and_receipt_never_report_environment_token(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    report, code, _ = installer.run(
        ["install", "--dcc-path", str(host), "--python", sys.executable, "--json", "--yes"]
    )

    secret = "test-token-that-must-never-be-reported"
    assert code == 0
    assert secret not in json.dumps(report)
    assert secret not in installer.receipt_path(install_root).read_text(encoding="utf-8")


def test_verify_requires_uxp_session_then_typed_readiness(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]
    _, code, _ = installer.run(["install", *common, "--yes"])
    assert code == 0
    monkeypatch.undo()
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(installer, "_python_import_check", lambda _python: {"success": True})
    monkeypatch.setattr(installer, "_bootstrap_check", lambda _root: {"success": True})
    monkeypatch.setattr(
        installer,
        "probe_premiere",
        lambda **_kwargs: PremiereStatus(True, version="25.6.0"),
    )
    observed = {}

    def ready(**kwargs):
        observed.update(kwargs)
        return {"success": True, "status": "ready"}

    monkeypatch.setattr(installer, "wait_for_sidecar_ready", ready)
    verified, verify_code, _ = installer.run(["verify", *common])

    assert verify_code == 0
    assert verified["verify"]["directly_usable"] is True
    assert observed["dcc_type"] == "premiere"
    assert observed["probe_tool"] == "premiere_project__get_status"


def test_missing_uxp_session_fails_closed_without_restart_claim(tmp_path, monkeypatch):
    _install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": False,
            "failure_stage": "uxp_session",
            "failure_reason": "Premiere bridge session is not connected",
        },
    )
    report, code, _ = installer.run(
        ["verify", "--dcc-path", str(host), "--python", sys.executable, "--json"]
    )

    assert code == 40
    assert report["status"] == "failed"
    assert report["verify"]["failure_stage"] == "uxp_session"
    assert len(report["next_steps"]) == 1
    assert report["next_steps"][0]["id"] == "load-uxp-plugin-and-verify"
    assert report["status"] != "requires_restart"


def test_uninstall_refuses_unknown_unreceipted_plugin(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    target = installer.plugin_path(install_root)
    target.mkdir(parents=True)
    (target / "user-file.txt").write_text("preserve", encoding="utf-8")

    report, code, _ = installer.run(
        [
            "uninstall",
            "--dcc-path",
            str(host),
            "--python",
            sys.executable,
            "--json",
            "--yes",
        ]
    )

    assert code == 10
    assert report["verify"]["failure_stage"] in {"partial", "receipt"}
    assert (target / "user-file.txt").read_text(encoding="utf-8") == "preserve"


def test_uninstall_uses_receipted_host_identity_when_host_is_gone(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    _, install_code, _ = installer.run(
        [
            "install",
            "--dcc-path",
            str(host),
            "--python",
            sys.executable,
            "--json",
            "--yes",
        ]
    )
    assert install_code == 0

    def reject_host_discovery(_value):
        raise AssertionError("receipt-only uninstall must not rediscover a removed host")

    monkeypatch.setattr(installer, "resolve_host", reject_host_discovery)
    removed, remove_code, _ = installer.run(
        ["uninstall", "--python", sys.executable, "--json", "--yes"]
    )

    assert remove_code == 0
    assert removed["host_source"] == "receipt"
    assert not installer.plugin_path(install_root).exists()


def _mark_runtime_as_receipted(install_root: Path, monkeypatch) -> Path:
    runtime = installer.runtime_path(install_root)
    cli = runtime / "bin" / "adobepy.exe"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(b"owned runtime")
    runtime_files = installer._file_manifest(runtime)
    receipt_file = installer.receipt_path(install_root)
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    receipt.update(
        {
            "runtime_owned": True,
            "runtime_path": str(runtime),
            "runtime_files": runtime_files,
            "runtime_digest": installer._manifest_digest(runtime_files),
            "adobepy_cli": str(cli),
        }
    )
    installer._write_json_atomic(receipt_file, receipt)
    monkeypatch.setenv("DCC_MCP_PREMIERE_ADOBEPY", str(cli))
    return cli


def test_status_detects_tampering_in_receipted_runtime(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]
    _, install_code, _ = installer.run(["install", *common, "--yes"])
    assert install_code == 0
    cli = _mark_runtime_as_receipted(install_root, monkeypatch)
    assert installer._installation_state(install_root) == "current"

    cli.write_bytes(b"tampered runtime")

    assert installer._installation_state(install_root) == "repair"


def test_upgrade_preserves_receipted_runtime_ownership(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]
    _, install_code, _ = installer.run(["install", *common, "--yes"])
    assert install_code == 0
    cli = _mark_runtime_as_receipted(install_root, monkeypatch)

    _, upgrade_code, _ = installer.run(["upgrade", *common, "--yes"])

    receipt = json.loads(installer.receipt_path(install_root).read_text(encoding="utf-8"))
    assert upgrade_code == 0
    assert receipt["runtime_owned"] is True
    assert Path(receipt["adobepy_cli"]) == cli


def test_uninstall_preserves_modified_receipted_runtime(tmp_path, monkeypatch):
    install_root, host = _prepare_lifecycle(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer,
        "verify_install",
        lambda *_args: {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
        },
    )
    common = ["--dcc-path", str(host), "--python", sys.executable, "--json"]
    _, install_code, _ = installer.run(["install", *common, "--yes"])
    assert install_code == 0
    cli = _mark_runtime_as_receipted(install_root, monkeypatch)
    cli.write_bytes(b"operator-modified runtime")

    report, uninstall_code, _ = installer.run(["uninstall", *common, "--yes"])

    assert uninstall_code == 10
    assert report["verify"]["failure_stage"] == "receipt"
    assert cli.is_file()
    assert installer.receipt_path(install_root).is_file()


def test_bridge_stage_rejects_an_incompatible_uxp_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("ADOBEPY_TOKEN", "test-token")
    destination = tmp_path / "bridge"
    (destination / "dist").mkdir(parents=True)
    (destination / "manifest.json").write_text(
        '{"manifestVersion":4,"host":{"app":"PR","minVersion":"25.6.0"}}',
        encoding="utf-8",
    )
    (destination / "dist" / "main.js").write_text("bridge", encoding="utf-8")
    (destination / "adobepy.config.js").write_text("config", encoding="utf-8")
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )

    with pytest.raises(installer.InstallFailure, match="manifest v5") as raised:
        installer._build_bridge(tmp_path / "adobepy.exe", destination)

    assert raised.value.exit_code == 30
    assert raised.value.stage == "bridge"


def test_linux_host_preflight_is_explicit(monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "linux")

    with pytest.raises(installer.InstallFailure, match="not available on Linux") as raised:
        installer.resolve_host(None)

    assert raised.value.exit_code == 10
    assert raised.value.stage == "platform"


def test_windows_version_resource_words_are_decoded_in_file_version_order():
    assert installer._format_windows_version(25 << 16 | 6, 3 << 16 | 17) == "25.6.3.17"
