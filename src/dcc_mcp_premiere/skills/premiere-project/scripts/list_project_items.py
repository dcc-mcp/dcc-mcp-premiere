"""List bounded Premiere project items."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import list_project_items
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere project items listed.", list_project_items, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
