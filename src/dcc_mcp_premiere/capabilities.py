"""Declared capabilities for the Premiere adapter."""

from __future__ import annotations


def premiere_capabilities():
    from dcc_mcp_core import DccCapabilities

    return DccCapabilities(
        scene_info=True,
        file_operations=True,
        selection=True,
        scene_manager=True,
        render_capture=True,
        hierarchy=True,
        has_embedded_python=False,
        bridge_kind="adobepy_broker",
        bridge_endpoint="http://127.0.0.1:47391",
        extensions={"official_uxp": True, "raw_eval_exposed": False},
    )


__all__ = ["premiere_capabilities"]
