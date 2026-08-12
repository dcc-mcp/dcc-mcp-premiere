"""Overwrite a project item into a Premiere sequence."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import overwrite_project_item
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere project item overwritten.", overwrite_project_item, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
