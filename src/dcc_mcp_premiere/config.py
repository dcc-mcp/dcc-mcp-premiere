"""Runtime configuration for the adobepy-backed Premiere adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_float(name: str, default: str, minimum: float) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError as error:
        raise ValueError(f"{name} must be numeric") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class PremiereConfig:
    broker_url: str | None = None
    token: str | None = None
    broker_path: str | None = None
    target: str = "default"
    timeout: float = 5.0
    poll_interval: float = 2.0

    @classmethod
    def from_env(cls) -> "PremiereConfig":
        return cls(
            broker_url=os.getenv("ADOBEPY_BROKER_URL"),
            token=os.getenv("ADOBEPY_TOKEN"),
            broker_path=os.getenv("ADOBEPY_BROKER_PATH"),
            target=os.getenv("ADOBEPY_TARGET", "default"),
            timeout=_positive_float("DCC_MCP_PREMIERE_BROKER_TIMEOUT_SECS", "5", 0.1),
            poll_interval=_positive_float("DCC_MCP_PREMIERE_BRIDGE_POLL_SECS", "2", 0.25),
        )


__all__ = ["PremiereConfig"]
