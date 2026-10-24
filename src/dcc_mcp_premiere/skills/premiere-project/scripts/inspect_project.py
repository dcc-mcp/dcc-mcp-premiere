"""Inspect the active Premiere project through the typed facade."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import inspect_project
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**_kwargs):
    return invoke("Premiere project inspected.", inspect_project)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
