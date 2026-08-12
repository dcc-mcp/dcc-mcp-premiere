"""Bounded Premiere context snapshots without media or project paths."""

from __future__ import annotations

from typing import Any, Callable

from adobe.core import BrokerClient
from adobe.premiere import Premiere
from dcc_mcp_core import DccContextSnapshot


def collect_context(
    *,
    broker_url: str | None,
    token: str | None,
    target: str,
    timeout: float,
    client_factory: Callable[..., Any] = BrokerClient,
    app_factory: Callable[..., Any] = Premiere,
) -> DccContextSnapshot:
    client = client_factory(
        broker_url=broker_url,
        token=token,
        target=target,
        timeout=timeout,
    )
    app = app_factory(client=client)
    project = app.project
    active_sequence = app.active_sequence
    return DccContextSnapshot(
        dcc="premiere",
        document={"name": project.name} if project is not None else None,
        active_object={"name": active_sequence.name} if active_sequence is not None else None,
        counts={
            "project_items": int(project.item_count),
            "sequences": len(project.sequences),
        }
        if project is not None
        else {},
        metadata={"version": str(app.version), "target": target},
    )


__all__ = ["collect_context"]
