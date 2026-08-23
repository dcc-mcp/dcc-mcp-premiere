"""Agent-first Premiere Install SOP v1 lifecycle."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from dcc_mcp_core.install_lifecycle import (
    inspect_install_root,
    safe_remove_tree,
    wait_for_sidecar_ready,
)

from .__version__ import __version__
from .install_contract import (
    INSTALL_EXIT_ACQUIRE,
    INSTALL_EXIT_INSTALL,
    INSTALL_EXIT_OK,
    INSTALL_EXIT_PREFLIGHT,
    INSTALL_EXIT_REQUIRES_RESTART,
    INSTALL_EXIT_VERIFY,
    INSTALL_SOP_SCHEMA_VERSION,
)
from .runtime import probe_premiere

MIN_CORE_VERSION = "0.19.45"
MIN_PREMIERE_VERSION = "25.6.0"
ADOBEPY_RUNTIME_VERSION = "0.6.2"
ADOBEPY_WINDOWS_URL = (
    "https://github.com/dcc-mcp/adobepy/releases/download/"
    "adobepy-v0.6.2/adobepy-0.6.2-windows-x64.zip"
)
ADOBEPY_WINDOWS_SHA256 = "9ef9abb5e034359f12e9ce248b0030e38d34c76df343eb2713f18036068719a7"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_FILES = 1_000
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024
MAX_RECEIPT_FILES = 1_000
RECEIPT_SCHEMA_VERSION = 1
VERBS = {"install", "status", "verify", "uninstall", "upgrade"}


class InstallFailure(ValueError):
    """Expected lifecycle failure with a stable public stage and exit code."""

    def __init__(self, exit_code: int, stage: str, reason: str):
        super().__init__(reason)
        self.exit_code = exit_code
        self.stage = stage
        self.reason = reason


@dataclass(frozen=True)
class HostInstall:
    path: Path
    version: str
    profile_path: Path
    source: str


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+(?:\.\d+)*)", value.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def _data_root() -> Path:
    override = os.getenv("DCC_MCP_PREMIERE_INSTALL_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return (base / "DCC-MCP" / "premiere").resolve()


def receipt_path(root: Optional[Path] = None) -> Path:
    return (root or _data_root()) / "receipts" / "premiere.json"


def plugin_path(root: Optional[Path] = None) -> Path:
    return (root or _data_root()) / "uxp-plugin"


def runtime_path(root: Optional[Path] = None) -> Path:
    return (root or _data_root()) / "runtime" / f"adobepy-{ADOBEPY_RUNTIME_VERSION}-windows-x64"


def bootstrap_log_dir(root: Optional[Path] = None) -> Path:
    return (root or _data_root()) / "bootstrap"


def _format_windows_version(ms: int, ls: int) -> str:
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def _windows_file_version(path: Path) -> str:
    if os.name != "nt":
        raise OSError("Windows version resources are unavailable on this platform")
    size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        raise OSError(f"Premiere executable has no version resource: {path}")
    buffer = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
        raise OSError(f"Could not read Premiere version resource: {path}")
    pointer = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(
        buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)
    ):
        raise OSError(f"Could not query Premiere version resource: {path}")

    class FixedFileInfo(ctypes.Structure):
        _fields_ = [
            ("dwSignature", ctypes.c_uint32),
            ("dwStrucVersion", ctypes.c_uint32),
            ("dwFileVersionMS", ctypes.c_uint32),
            ("dwFileVersionLS", ctypes.c_uint32),
            ("dwProductVersionMS", ctypes.c_uint32),
            ("dwProductVersionLS", ctypes.c_uint32),
            ("dwFileFlagsMask", ctypes.c_uint32),
            ("dwFileFlags", ctypes.c_uint32),
            ("dwFileOS", ctypes.c_uint32),
            ("dwFileType", ctypes.c_uint32),
            ("dwFileSubtype", ctypes.c_uint32),
            ("dwFileDateMS", ctypes.c_uint32),
            ("dwFileDateLS", ctypes.c_uint32),
        ]

    fixed = ctypes.cast(pointer, ctypes.POINTER(FixedFileInfo)).contents
    return _format_windows_version(fixed.dwFileVersionMS, fixed.dwFileVersionLS)


def _read_host_version(path: Path) -> str:
    app = (
        path
        if path.suffix.lower() == ".app"
        else next(
            (parent for parent in path.parents if parent.suffix.lower() == ".app"),
            None,
        )
    )
    if app is not None:
        info = app / "Contents" / "Info.plist"
        try:
            with info.open("rb") as stream:
                payload = plistlib.load(stream)
        except (OSError, plistlib.InvalidFileException) as exc:
            raise OSError(f"Could not read Premiere application metadata: {info}") from exc
        version = payload.get("CFBundleShortVersionString")
        if not isinstance(version, str) or not _version_tuple(version):
            raise OSError(f"Premiere application version is missing: {info}")
        return version
    return _windows_file_version(path)


def _host_profile(version: str) -> Path:
    major = _version_tuple(version)[0]
    if os.name == "nt":
        base = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / "Adobe" / "Premiere Pro" / f"{major}.0"
    return Path.home() / "Documents" / "Adobe" / "Premiere Pro" / f"{major}.0"


def _host_candidates() -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.getenv(variable)
            if not root:
                continue
            adobe = Path(root) / "Adobe"
            if adobe.is_dir():
                candidates.extend(adobe.glob("Adobe Premiere Pro */Adobe Premiere Pro.exe"))
    elif sys.platform == "darwin":
        candidates.extend(Path("/Applications").glob("Adobe Premiere Pro *.app"))
    return sorted(candidates, reverse=True)


def resolve_host(value: Optional[Path]) -> HostInstall:
    if sys.platform.startswith("linux"):
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "platform",
            "Adobe Premiere Pro and its UXP host are not available on Linux",
        )
    explicit = value is not None
    choices = [value.expanduser().resolve()] if value is not None else _host_candidates()
    failures: list[str] = []
    for choice in choices:
        path = choice
        if path.suffix.lower() == ".app":
            valid = path.is_dir() and (path / "Contents" / "Info.plist").is_file()
        else:
            valid = path.is_file()
        if not valid:
            failures.append(f"Premiere host not found: {path}")
            continue
        try:
            version = _read_host_version(path)
        except OSError as exc:
            failures.append(str(exc))
            continue
        if _version_tuple(version) < _version_tuple(MIN_PREMIERE_VERSION):
            failures.append(
                f"Premiere Pro {version} is unsupported; version {MIN_PREMIERE_VERSION} or newer is required"
            )
            continue
        return HostInstall(
            path, version, _host_profile(version), "flag" if explicit else "detected"
        )
    reason = failures[0] if failures else "Adobe Premiere Pro 25.6 or newer was not detected"
    raise InstallFailure(INSTALL_EXIT_PREFLIGHT, "host", reason)


def _resolve_python(value: Optional[Path]) -> tuple[Path, str]:
    source = "running-interpreter"
    selected = value
    if selected is not None:
        source = "flag"
    elif os.getenv("DCC_MCP_INSTALL_PYTHON"):
        selected = Path(os.environ["DCC_MCP_INSTALL_PYTHON"])
        source = "environment"
    path = (selected or Path(sys.executable)).expanduser().resolve()
    if not path.is_file():
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT, "python", f"Python interpreter not found: {path}"
        )
    return path, source


def _target_versions(python: Path) -> dict[str, str]:
    code = (
        "import importlib.metadata as m,json,sys; "
        "print(json.dumps({'python':'.'.join(map(str,sys.version_info[:3])),"
        "'core':m.version('dcc-mcp-core'),'adapter':m.version('dcc-mcp-premiere')}))"
    )
    try:
        completed = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            f"Cannot inspect target interpreter: {exc}",
        ) from exc
    if completed.returncode:
        reason = completed.stderr.strip().splitlines()
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            reason[-1] if reason else "Target package metadata query failed",
        )
    try:
        versions = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            "Target interpreter returned invalid package metadata",
        ) from exc
    if _version_tuple(versions["python"]) < (3, 9):
        raise InstallFailure(INSTALL_EXIT_PREFLIGHT, "python", "Python 3.9 or newer is required")
    if _version_tuple(versions["core"]) < _version_tuple(MIN_CORE_VERSION):
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "core",
            f"dcc-mcp-core {versions['core']} is unsupported; version {MIN_CORE_VERSION} or newer is required",
        )
    if versions["adapter"] != __version__:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "adapter",
            f"Target interpreter has dcc-mcp-premiere {versions['adapter']}; expected {__version__}",
        )
    return versions


def _file_manifest(root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise InstallFailure(
                INSTALL_EXIT_INSTALL, "artifact", f"Symbolic link is not allowed: {path}"
            )
        if not path.is_file():
            continue
        data = path.read_bytes()
        total += len(data)
        if len(files) >= MAX_RECEIPT_FILES or total > MAX_EXTRACTED_BYTES:
            raise InstallFailure(
                INSTALL_EXIT_INSTALL, "artifact", "Install payload exceeds bounded limits"
            )
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    return files


def _manifest_digest(files: list[dict[str, Any]]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_receipt(root: Path) -> Optional[dict[str, Any]]:
    path = receipt_path(root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT, "receipt", f"Install receipt is unreadable: {path}"
        ) from exc
    if (
        payload.get("schema_version") != RECEIPT_SCHEMA_VERSION
        or payload.get("dcc_type") != "premiere"
    ):
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT, "receipt", f"Unsupported Premiere receipt: {path}"
        )
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _installation_state(root: Path) -> str:
    target = plugin_path(root)
    receipt = _read_receipt(root)
    if not target.exists():
        return "repair" if receipt else "fresh"
    if receipt is None:
        return "partial"
    if Path(receipt.get("plugin_path", "")).resolve() != target.resolve():
        return "partial"
    try:
        actual = _manifest_digest(_file_manifest(target))
    except (OSError, InstallFailure):
        return "repair"
    if actual != receipt.get("plugin_digest"):
        return "repair"
    if receipt.get("runtime_owned"):
        value = receipt.get("runtime_path")
        if not isinstance(value, str) or Path(value).resolve() != runtime_path(root).resolve():
            return "partial"
        try:
            runtime_files = _file_manifest(runtime_path(root))
        except (OSError, InstallFailure):
            return "repair"
        if runtime_files != receipt.get("runtime_files"):
            return "repair"
        if _manifest_digest(runtime_files) != receipt.get("runtime_digest"):
            return "repair"
    if receipt.get("adapter_version") != __version__:
        return "upgrade"
    return "current"


def _download_runtime(archive: Path) -> None:
    request = urllib.request.Request(
        ADOBEPY_WINDOWS_URL, headers={"User-Agent": "dcc-mcp-premiere-installer/1"}
    )
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response, archive.open("wb") as output:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_ARCHIVE_BYTES:
                raise InstallFailure(
                    INSTALL_EXIT_ACQUIRE, "acquire", "Pinned adobepy archive is oversized"
                )
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise InstallFailure(
                        INSTALL_EXIT_ACQUIRE, "acquire", "Pinned adobepy archive is oversized"
                    )
                digest.update(chunk)
                output.write(chunk)
    except InstallFailure:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise InstallFailure(
            INSTALL_EXIT_ACQUIRE, "acquire", f"Could not acquire pinned adobepy runtime: {exc}"
        ) from exc
    if digest.hexdigest() != ADOBEPY_WINDOWS_SHA256:
        raise InstallFailure(
            INSTALL_EXIT_ACQUIRE, "acquire", "Pinned adobepy runtime SHA-256 mismatch"
        )


def _extract_runtime(archive: Path, destination: Path) -> tuple[Path, Path]:
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_ARCHIVE_FILES:
                raise InstallFailure(
                    INSTALL_EXIT_ACQUIRE, "acquire", "Pinned runtime contains too many files"
                )
            total = sum(member.file_size for member in members)
            if total > MAX_EXTRACTED_BYTES:
                raise InstallFailure(
                    INSTALL_EXIT_ACQUIRE, "acquire", "Pinned runtime expands beyond bounded limits"
                )
            for member in members:
                relative = Path(member.filename)
                mode = member.external_attr >> 16
                if relative.is_absolute() or ".." in relative.parts or stat.S_ISLNK(mode):
                    raise InstallFailure(
                        INSTALL_EXIT_ACQUIRE, "acquire", "Pinned runtime contains an unsafe path"
                    )
            bundle.extractall(destination)
    except InstallFailure:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise InstallFailure(
            INSTALL_EXIT_ACQUIRE, "acquire", f"Could not extract pinned runtime: {exc}"
        ) from exc
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise InstallFailure(
            INSTALL_EXIT_ACQUIRE, "acquire", "Pinned runtime archive has an unexpected layout"
        )
    cli = roots[0] / "bin" / "adobepy.exe"
    if not cli.is_file():
        raise InstallFailure(
            INSTALL_EXIT_ACQUIRE, "acquire", "Pinned runtime does not contain adobepy.exe"
        )
    return roots[0], cli


def _configured_adobepy() -> Optional[Path]:
    configured = os.getenv("DCC_MCP_PREMIERE_ADOBEPY") or os.getenv("ADOBEPY_BROKER_PATH")
    candidate = Path(configured).expanduser().resolve() if configured else None
    if candidate is None:
        found = shutil.which("adobepy")
        candidate = Path(found).resolve() if found else None
    return candidate if candidate is not None and candidate.is_file() else None


def _build_bridge(cli: Path, destination: Path) -> None:
    token = os.getenv("ADOBEPY_TOKEN")
    if not token:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "token",
            "ADOBEPY_TOKEN must be configured in the environment before installation",
        )
    broker_url = os.getenv("ADOBEPY_BROKER_URL", "http://127.0.0.1:47391")
    target = os.getenv("ADOBEPY_TARGET", "default")
    environment = os.environ.copy()
    environment["ADOBEPY_TOKEN"] = token
    completed = subprocess.run(
        [
            str(cli),
            "install-bridge",
            "premiere",
            "--dest",
            str(destination),
            "--broker-url",
            broker_url,
            "--target",
            target,
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=environment,
    )
    if completed.returncode:
        reason = completed.stderr.strip().splitlines()
        raise InstallFailure(
            INSTALL_EXIT_INSTALL,
            "bridge",
            reason[-1] if reason else "adobepy could not stage the Premiere UXP bridge",
        )
    required = [
        destination / "manifest.json",
        destination / "dist" / "main.js",
        destination / "adobepy.config.js",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise InstallFailure(INSTALL_EXIT_INSTALL, "bridge", "Staged UXP bridge is incomplete")
    try:
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallFailure(
            INSTALL_EXIT_INSTALL, "bridge", "Staged UXP manifest is invalid"
        ) from exc
    if manifest.get("host", {}).get("app") != "PR":
        raise InstallFailure(
            INSTALL_EXIT_INSTALL, "bridge", "Staged UXP manifest does not target Premiere"
        )
    if manifest.get("manifestVersion") != 5:
        raise InstallFailure(
            INSTALL_EXIT_INSTALL,
            "bridge",
            "Staged UXP manifest must use Adobe manifest v5",
        )
    if _version_tuple(str(manifest.get("host", {}).get("minVersion", ""))) < _version_tuple(
        MIN_PREMIERE_VERSION
    ):
        raise InstallFailure(
            INSTALL_EXIT_INSTALL, "bridge", "Staged UXP manifest has an unsafe host version floor"
        )


def _restore_receipt(path: Path, old: Optional[bytes]) -> None:
    if old is None:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(old)


def _lock_failure(exc: OSError) -> bool:
    return os.name == "nt" and (
        getattr(exc, "winerror", None) in {5, 32, 33} or isinstance(exc, PermissionError)
    )


def _execute_install(report: dict[str, Any], timeout: float) -> tuple[dict[str, Any], int]:
    root = Path(report["install_root"])
    state = report["installation_state"]
    if state == "partial":
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "partial",
            "Refusing to replace an unreceipted or mismatched Premiere plugin tree",
        )
    if report["verb"] == "upgrade" and state == "fresh":
        raise InstallFailure(INSTALL_EXIT_PREFLIGHT, "upgrade", "Nothing is installed; use install")
    if state == "current" and report["verb"] == "install":
        report["verify"] = verify_install(report, timeout)
        report["status"] = "ok" if report["verify"]["directly_usable"] else "partial"
        if not report["verify"]["directly_usable"]:
            report["next_steps"] = [_uxp_next_step(report)]
            return report, INSTALL_EXIT_VERIFY
        return report, INSTALL_EXIT_OK

    token = os.getenv("ADOBEPY_TOKEN")
    if not token:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT, "token", "ADOBEPY_TOKEN must be configured in the environment"
        )
    root.parent.mkdir(parents=True, exist_ok=True)
    transaction = root.parent / f".{root.name}.{uuid.uuid4().hex}.transaction"
    transaction.mkdir()
    bridge_stage = transaction / "uxp-plugin"
    runtime_stage: Optional[Path] = None
    previous_receipt = _read_receipt(root)
    previous_runtime_owned = False
    if previous_receipt is not None and previous_receipt.get("runtime_owned"):
        previous_runtime = previous_receipt.get("runtime_path")
        if (
            isinstance(previous_runtime, str)
            and Path(previous_runtime).resolve() == runtime_path(root).resolve()
        ):
            try:
                previous_runtime_files = _file_manifest(runtime_path(root))
                previous_runtime_owned = previous_runtime_files == previous_receipt.get(
                    "runtime_files"
                ) and _manifest_digest(previous_runtime_files) == previous_receipt.get(
                    "runtime_digest"
                )
            except (OSError, InstallFailure):
                previous_runtime_owned = False
    cli = _configured_adobepy()
    if (
        previous_receipt is not None
        and previous_receipt.get("runtime_owned")
        and not previous_runtime_owned
    ):
        cli = None
    try:
        if cli is None:
            if os.name != "nt":
                raise InstallFailure(
                    INSTALL_EXIT_PREFLIGHT,
                    "runtime",
                    "No official adobepy runtime bundle exists for this platform; configure DCC_MCP_PREMIERE_ADOBEPY",
                )
            archive = transaction / "adobepy-runtime.zip"
            extracted = transaction / "runtime"
            _download_runtime(archive)
            runtime_stage, cli = _extract_runtime(archive, extracted)
        _build_bridge(cli, bridge_stage)
        targets: list[tuple[Path, Path, str]] = [(bridge_stage, plugin_path(root), "plugin")]
        if runtime_stage is not None:
            targets.append((runtime_stage, runtime_path(root), "runtime"))
        for _stage, target, _kind in targets:
            lock = inspect_install_root(target)
            if lock.get("requires_restart"):
                raise InstallFailure(
                    INSTALL_EXIT_REQUIRES_RESTART,
                    "lock",
                    lock.get("recommended_next_action", "Premiere restart is required"),
                )
        path = receipt_path(root)
        old_receipt = path.read_bytes() if path.is_file() else None
        swaps: list[dict[str, Any]] = []
        try:
            for stage, target, kind in targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = (
                    target.parent / f".{target.name}.{uuid.uuid4().hex}.backup"
                    if target.exists()
                    else None
                )
                swap = {
                    "target": target,
                    "stage": stage,
                    "backup": backup,
                    "kind": kind,
                    "installed": False,
                }
                if backup is not None:
                    os.replace(target, backup)
                swaps.append(swap)
                os.replace(stage, target)
                swap["installed"] = True
            plugin_files = _file_manifest(plugin_path(root))
            runtime_owned = runtime_stage is not None or previous_runtime_owned
            runtime_files = _file_manifest(runtime_path(root)) if runtime_owned else []
            installed_cli = (
                runtime_path(root) / "bin" / "adobepy.exe" if runtime_stage is not None else cli
            )
            _write_json_atomic(
                path,
                {
                    "schema_version": RECEIPT_SCHEMA_VERSION,
                    "dcc_type": "premiere",
                    "adapter_version": __version__,
                    "core_version": report["core_version"],
                    "premiere_version": report["premiere_version"],
                    "dcc_path": report["dcc_path"],
                    "profile_path": report["profile_path"],
                    "python": report["python"],
                    "python_version": report["python_version"],
                    "plugin_path": str(plugin_path(root)),
                    "plugin_digest": _manifest_digest(plugin_files),
                    "plugin_files": plugin_files,
                    "runtime_owned": runtime_owned,
                    "runtime_path": str(runtime_path(root)) if runtime_owned else None,
                    "runtime_digest": _manifest_digest(runtime_files) if runtime_owned else None,
                    "runtime_files": runtime_files,
                    "adobepy_cli": str(installed_cli),
                    "broker_url": os.getenv("ADOBEPY_BROKER_URL", "http://127.0.0.1:47391"),
                    "target": os.getenv("ADOBEPY_TARGET", "default"),
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            for swap in reversed(swaps):
                target = swap["target"]
                backup = swap["backup"]
                failed = target.parent / f".{target.name}.{uuid.uuid4().hex}.failed"
                if swap["installed"] and target.exists():
                    os.replace(target, failed)
                    safe_remove_tree(failed)
                if backup is not None and backup.exists():
                    os.replace(backup, target)
            _restore_receipt(path, old_receipt)
            if isinstance(exc, InstallFailure):
                raise
            code = (
                INSTALL_EXIT_REQUIRES_RESTART
                if isinstance(exc, OSError) and _lock_failure(exc)
                else INSTALL_EXIT_INSTALL
            )
            raise InstallFailure(code, "install", f"Install rolled back: {exc}") from exc
        for swap in swaps:
            backup = swap["backup"]
            if backup is not None and backup.exists():
                removed = safe_remove_tree(backup)
                if not removed.get("success"):
                    code = (
                        INSTALL_EXIT_REQUIRES_RESTART
                        if removed.get("requires_restart")
                        else INSTALL_EXIT_INSTALL
                    )
                    raise InstallFailure(
                        code, "cleanup", removed.get("message", "Backup cleanup failed")
                    )
    finally:
        if transaction.exists():
            removed = safe_remove_tree(transaction)
            if not removed.get("success") and sys.exc_info()[0] is None:
                code = (
                    INSTALL_EXIT_REQUIRES_RESTART
                    if removed.get("requires_restart")
                    else INSTALL_EXIT_INSTALL
                )
                raise InstallFailure(
                    code, "cleanup", removed.get("message", "Transaction cleanup failed")
                )

    report["steps"][-1] = {"id": report["verb"], "status": "ok", "previous_state": state}
    report["verify"] = verify_install(report, timeout)
    if report["verify"]["directly_usable"]:
        report["status"] = "ok"
        report["next_steps"] = []
        return report, INSTALL_EXIT_OK
    report["status"] = "partial"
    report["next_steps"] = [_uxp_next_step(report)]
    return report, INSTALL_EXIT_VERIFY


def _manifest_check(root: Path, expected: list[dict[str, Any]], digest: str) -> dict[str, Any]:
    if not root.is_dir():
        return {"success": False, "reason": f"Installed tree is missing: {root}"}
    actual_files = _file_manifest(root)
    actual_digest = _manifest_digest(actual_files)
    return {
        "success": actual_files == expected and actual_digest == digest,
        "expected_sha256": digest,
        "actual_sha256": actual_digest,
        "reason": None
        if actual_files == expected and actual_digest == digest
        else "Installed files differ from receipt",
    }


def _python_import_check(python: Path) -> dict[str, Any]:
    code = (
        "import json,dcc_mcp_premiere; "
        "print(json.dumps({'success':True,'version':dcc_mcp_premiere.__version__}))"
    )
    try:
        completed = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "reason": str(exc)}
    if completed.returncode:
        lines = completed.stderr.strip().splitlines()
        return {"success": False, "reason": lines[-1] if lines else "Adapter import failed"}
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"success": False, "reason": "Target interpreter returned invalid import output"}
    if result.get("version") != __version__:
        return {"success": False, "reason": "Target adapter version does not match", **result}
    return result


def _bootstrap_check(root: Path) -> dict[str, Any]:
    directory = bootstrap_log_dir(root)
    marker = directory / "last-success.json"
    errors = (
        sorted(
            directory.glob("dcc-mcp-premiere.*.host-errors.log"),
            key=lambda path: path.stat().st_mtime,
        )
        if directory.is_dir()
        else []
    )
    latest_error = errors[-1] if errors else None
    if latest_error is not None and (
        not marker.is_file() or latest_error.stat().st_mtime > marker.stat().st_mtime
    ):
        return {
            "success": False,
            "reason": f"A newer Premiere bootstrap error is recorded: {latest_error.name}",
        }
    return {"success": True, "log_dir": str(directory)}


def verify_install(report: dict[str, Any], timeout: float) -> dict[str, Any]:
    root = Path(report["install_root"])
    result: dict[str, Any] = {
        "directly_usable": False,
        "failure_stage": None,
        "failure_reason": None,
    }
    try:
        receipt = _read_receipt(root)
    except InstallFailure as exc:
        result.update(failure_stage=exc.stage, failure_reason=exc.reason)
        return result
    if receipt is None:
        result.update(
            failure_stage="artifact", failure_reason="Premiere install receipt is missing"
        )
        return result
    if Path(receipt.get("plugin_path", "")).resolve() != plugin_path(root).resolve():
        result.update(
            failure_stage="artifact",
            failure_reason="Receipt plugin path does not match install root",
        )
        return result
    artifact = _manifest_check(
        plugin_path(root), receipt.get("plugin_files", []), receipt.get("plugin_digest", "")
    )
    result["artifact"] = artifact
    if not artifact["success"]:
        result.update(failure_stage="artifact", failure_reason=artifact["reason"])
        return result
    imported = _python_import_check(Path(report["python"]))
    result["import"] = imported
    if not imported.get("success"):
        result.update(failure_stage="import", failure_reason=imported.get("reason"))
        return result
    bootstrap = _bootstrap_check(root)
    result["bootstrap"] = bootstrap
    if not bootstrap["success"]:
        result.update(failure_stage="bootstrap", failure_reason=bootstrap["reason"])
        return result
    token = os.getenv("ADOBEPY_TOKEN")
    if not token:
        result.update(failure_stage="broker", failure_reason="ADOBEPY_TOKEN is not configured")
        return result
    bridge = probe_premiere(
        broker_url=os.getenv("ADOBEPY_BROKER_URL"),
        token=token,
        target=os.getenv("ADOBEPY_TARGET", "default"),
        timeout=min(max(timeout, 0.1), 10.0),
    )
    result["uxp_session"] = {
        "success": bridge.ready,
        "version": bridge.version,
        "reason": bridge.reason,
    }
    if not bridge.ready:
        result.update(
            failure_stage="uxp_session",
            failure_reason=bridge.reason or "Premiere UXP session is not connected",
        )
        return result
    readiness = wait_for_sidecar_ready(
        dcc_type="premiere",
        timeout_secs=max(0.0, timeout),
        probe_tool="premiere_project__get_status",
    )
    result["readiness"] = readiness
    if not readiness.get("success"):
        result.update(
            failure_stage="readiness",
            failure_reason=readiness.get("message", "Typed Premiere readiness probe failed"),
        )
        return result
    result["directly_usable"] = True
    return result


def _uxp_next_step(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("verb") in {"install", "upgrade"}:
        command = ["dcc-mcp-premiere", "serve"]
        description = (
            "In Adobe UXP Developer Tool, add and load the Premiere plugin at "
            f"{plugin_path(Path(report['install_root']))}, then start the adapter with this command."
        )
    else:
        command = [
            "dcc-mcp-premiere",
            "verify",
            "--dcc-path",
            report["dcc_path"],
            "--python",
            report["python"],
            "--json",
        ]
        description = (
            "In Adobe UXP Developer Tool, add and load the Premiere plugin at "
            f"{plugin_path(Path(report['install_root']))}, then run this verification command."
        )
    return {
        "id": "load-uxp-plugin-and-verify",
        "description": description,
        "command": command,
        "why": "Adobe requires the unsigned development UXP plugin to be loaded by UXP Developer Tool.",
    }


def _execute_uninstall(report: dict[str, Any]) -> tuple[dict[str, Any], int]:
    root = Path(report["install_root"])
    receipt = _read_receipt(root)
    target = plugin_path(root)
    if receipt is None and not target.exists():
        report["status"] = "ok"
        report["steps"][-1] = {"id": "uninstall", "status": "already-absent"}
        return report, INSTALL_EXIT_OK
    if receipt is None:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT, "receipt", "Refusing to remove an unreceipted Premiere plugin"
        )
    artifact = _manifest_check(
        target, receipt.get("plugin_files", []), receipt.get("plugin_digest", "")
    )
    if not artifact["success"]:
        raise InstallFailure(
            INSTALL_EXIT_PREFLIGHT,
            "receipt",
            "Refusing to remove files that differ from the receipt",
        )
    owned = [target]
    if receipt.get("runtime_owned"):
        runtime = Path(receipt.get("runtime_path", ""))
        if runtime.resolve() != runtime_path(root).resolve():
            raise InstallFailure(
                INSTALL_EXIT_PREFLIGHT,
                "receipt",
                "Receipt runtime path does not match install root",
            )
        runtime_artifact = _manifest_check(
            runtime,
            receipt.get("runtime_files", []),
            receipt.get("runtime_digest", ""),
        )
        if not runtime_artifact["success"]:
            raise InstallFailure(
                INSTALL_EXIT_PREFLIGHT,
                "receipt",
                "Refusing to remove runtime files that differ from the receipt",
            )
        owned.append(runtime)
    for path in owned:
        lock = inspect_install_root(path)
        if lock.get("requires_restart"):
            raise InstallFailure(
                INSTALL_EXIT_REQUIRES_RESTART,
                "lock",
                lock.get("recommended_next_action", "Premiere restart is required"),
            )
    moved: list[tuple[Path, Path]] = []
    try:
        for path in owned:
            if not path.exists():
                continue
            quarantine = path.parent / f".{path.name}.{uuid.uuid4().hex}.uninstall"
            os.replace(path, quarantine)
            moved.append((path, quarantine))
        for _path, quarantine in moved:
            removed = safe_remove_tree(quarantine)
            if not removed.get("success"):
                raise OSError(removed.get("message", "Could not remove receipted tree"))
        receipt_path(root).unlink()
    except OSError as exc:
        for path, quarantine in reversed(moved):
            if quarantine.exists() and not path.exists():
                os.replace(quarantine, path)
        code = INSTALL_EXIT_REQUIRES_RESTART if _lock_failure(exc) else INSTALL_EXIT_INSTALL
        raise InstallFailure(code, "uninstall", f"Uninstall failed: {exc}") from exc
    report["status"] = "ok"
    report["steps"][-1] = {"id": "uninstall", "status": "ok"}
    report["verify"] = {"directly_usable": False, "failure_stage": None, "failure_reason": None}
    return report, INSTALL_EXIT_OK


def plan(verb: str, dcc_path: Optional[Path], python_path: Optional[Path]) -> dict[str, Any]:
    root = _data_root()
    existing_receipt = _read_receipt(root)
    if verb == "uninstall" and dcc_path is None and existing_receipt is not None:
        host = HostInstall(
            Path(existing_receipt["dcc_path"]),
            str(existing_receipt["premiere_version"]),
            Path(existing_receipt["profile_path"]),
            "receipt",
        )
    else:
        host = resolve_host(dcc_path)
    python, python_source = _resolve_python(python_path)
    versions = _target_versions(python)
    state = _installation_state(root)
    report = {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": "planned",
        "dcc_type": "premiere",
        "verb": verb,
        "adapter_version": __version__,
        "core_version": versions["core"],
        "python_version": versions["python"],
        "steps": [
            {"id": "preflight", "status": "ok"},
            {"id": "resolve-host", "status": "ok"},
            {"id": "resolve-python", "status": "ok"},
            {"id": verb, "status": "planned"},
        ],
        "next_steps": [],
        "receipt_path": str(receipt_path(root)),
        "verify": {"directly_usable": False, "failure_stage": None, "failure_reason": None},
        "dcc_path": str(host.path),
        "premiere_version": host.version,
        "profile_path": str(host.profile_path),
        "host_source": host.source,
        "python": str(python),
        "python_source": python_source,
        "install_root": str(root),
        "plugin_path": str(plugin_path(root)),
        "installation_state": state,
        "token_configured": bool(os.getenv("ADOBEPY_TOKEN")),
        "platform": sys.platform,
        "uxp_manifest_version": 5,
        "uxp_min_version": MIN_PREMIERE_VERSION,
        "adobepy_runtime_version": ADOBEPY_RUNTIME_VERSION,
    }
    if verb in {"install", "upgrade", "uninstall"}:
        report["next_steps"] = [
            {
                "id": f"execute-{verb}",
                "description": f"Execute the validated Premiere {verb} plan.",
                "command": [
                    "dcc-mcp-premiere",
                    verb,
                    "--dcc-path",
                    str(host.path),
                    "--python",
                    str(python),
                    "--json",
                    "--yes",
                ],
                "why": "Planning is non-mutating.",
            }
        ]
    return report


def _failure_result(verb: str, failure: InstallFailure, args: Any) -> dict[str, Any]:
    command = ["dcc-mcp-premiere", verb]
    if getattr(args, "dcc_path", None) is not None:
        command.extend(["--dcc-path", str(args.dcc_path)])
    if getattr(args, "python", None) is not None:
        command.extend(["--python", str(args.python)])
    command.append("--json")
    return {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": "requires_restart"
        if failure.exit_code == INSTALL_EXIT_REQUIRES_RESTART
        else "failed",
        "dcc_type": "premiere",
        "verb": verb,
        "adapter_version": __version__,
        "core_version": "unknown",
        "steps": [{"id": failure.stage, "status": "failed", "message": failure.reason}],
        "next_steps": [
            {
                "id": f"retry-{verb}",
                "description": f"Correct the reported {failure.stage} failure and retry.",
                "command": command,
                "why": failure.reason,
            }
        ],
        "receipt_path": str(receipt_path()),
        "verify": {
            "directly_usable": False,
            "failure_stage": failure.stage,
            "failure_reason": failure.reason,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DCC-MCP Premiere lifecycle")
    subparsers = parser.add_subparsers(dest="verb", required=True)
    for verb in sorted(VERBS):
        command = subparsers.add_parser(verb)
        command.add_argument("--json", action="store_true", dest="as_json")
        command.add_argument("--yes", action="store_true")
        command.add_argument("--dry-run", action="store_true")
        command.add_argument("--dcc-path", type=Path)
        command.add_argument("--python", type=Path)
        command.add_argument("--ready-timeout", type=float, default=0.0, help=argparse.SUPPRESS)
    return parser


def run(argv: Sequence[str]) -> tuple[dict[str, Any], int, bool]:
    args = _parser().parse_args(list(argv))
    report: Optional[dict[str, Any]] = None
    try:
        report = plan(args.verb, args.dcc_path, args.python)
        mutating = args.verb in {"install", "upgrade", "uninstall"}
        if args.dry_run or (mutating and not args.yes):
            return report, INSTALL_EXIT_OK, args.as_json
        if args.verb in {"install", "upgrade"}:
            report, code = _execute_install(report, max(0.0, args.ready_timeout))
        elif args.verb == "uninstall":
            report, code = _execute_uninstall(report)
        elif args.verb == "verify":
            report["verify"] = verify_install(report, max(0.0, args.ready_timeout))
            report["status"] = "ok" if report["verify"]["directly_usable"] else "failed"
            if report["status"] == "failed":
                report["next_steps"] = [_uxp_next_step(report)]
            code = INSTALL_EXIT_OK if report["status"] == "ok" else INSTALL_EXIT_VERIFY
        else:
            state = report["installation_state"]
            report["status"] = "ok" if state in {"fresh", "current"} else "partial"
            report["steps"][-1] = {
                "id": "status",
                "status": report["status"],
                "installation_state": state,
            }
            code = INSTALL_EXIT_OK if state in {"fresh", "current"} else INSTALL_EXIT_PREFLIGHT
        return report, code, args.as_json
    except InstallFailure as exc:
        return _failure_result(args.verb, exc, args), exc.exit_code, args.as_json
    except OSError as exc:
        code = (
            INSTALL_EXIT_INSTALL
            if report is not None and args.verb in {"install", "upgrade", "uninstall"}
            else INSTALL_EXIT_PREFLIGHT
        )
        failure = InstallFailure(code, args.verb, f"{exc.__class__.__name__}: {exc}")
        return _failure_result(args.verb, failure, args), code, args.as_json


def runtime_cli_from_receipt() -> Optional[str]:
    try:
        receipt = _read_receipt(_data_root())
    except InstallFailure:
        return None
    if receipt is None:
        return None
    value = receipt.get("adobepy_cli")
    path = Path(value) if isinstance(value, str) else None
    return str(path) if path is not None and path.is_file() else None


__all__ = [
    "ADOBEPY_RUNTIME_VERSION",
    "HostInstall",
    "InstallFailure",
    "MIN_CORE_VERSION",
    "MIN_PREMIERE_VERSION",
    "plan",
    "plugin_path",
    "receipt_path",
    "resolve_host",
    "run",
    "runtime_cli_from_receipt",
    "verify_install",
]
