"""Host-specific readiness for the adobepy-backed Premiere adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from adobe.core import BrokerClient
from adobe.premiere import Premiere

REQUIRED_METHODS: Mapping[str, tuple[str, ...]] = {
    "app": ("getVersion",),
    "project": (
        "getActive",
        "getSequences",
        "getActiveSequence",
        "getRootItem",
        "save",
        "saveAs",
        "createSequence",
        "importFiles",
    ),
    "projectItem": ("getChildren", "getSelected", "findByMediaPath"),
    "bin": ("create",),
    "sequence": (
        "getVideoTracks",
        "getAudioTracks",
        "insertProjectItem",
        "overwriteProjectItem",
    ),
    "track": ("getClips",),
    "clip": ("getSelected",),
    "marker": ("getMarkers", "create"),
    "encoder": ("getManager", "getPresets", "getExportFileExtension", "exportSequence"),
    "export": ("getExporter", "exportFrame"),
}


@dataclass(frozen=True)
class PremiereStatus:
    ready: bool
    reason: str = ""
    version: str | None = None
    target: str = "default"


def _matching_session(payloads: list[Mapping[str, Any]], target: str):
    for payload in payloads:
        capabilities = payload.get("capabilities", {})
        if capabilities.get("host") == "premiere" and payload.get("target", "default") == target:
            return payload
    return None


def _missing_methods(capabilities: Mapping[str, Any]) -> list[str]:
    advertised = capabilities.get("methods", {})
    return [
        f"{namespace}.{method}"
        for namespace, methods in REQUIRED_METHODS.items()
        for method in methods
        if method not in advertised.get(namespace, ())
    ]


def probe_premiere(
    *,
    broker_url: str | None = None,
    token: str | None = None,
    target: str = "default",
    timeout: float = 5.0,
    client: BrokerClient | None = None,
    app_factory: Callable[..., Any] = Premiere,
) -> PremiereStatus:
    """Require the complete typed bridge contract and one real version RPC."""

    active_client = client or BrokerClient(
        broker_url=broker_url,
        token=token,
        target=target,
        timeout=timeout,
    )
    try:
        session = _matching_session(active_client.capabilities(), target)
    except Exception as error:
        return PremiereStatus(False, str(error), target=target)
    if session is None:
        return PremiereStatus(False, "premiere bridge session is not connected", target=target)
    missing = _missing_methods(session.get("capabilities", {}))
    if missing:
        return PremiereStatus(
            False,
            "missing bridge methods: " + ", ".join(missing),
            target=target,
        )
    try:
        version = str(app_factory(client=active_client).version)
    except Exception as error:
        return PremiereStatus(False, str(error), target=target)
    return PremiereStatus(True, version=version, target=target)


__all__ = ["PremiereStatus", "REQUIRED_METHODS", "probe_premiere"]
