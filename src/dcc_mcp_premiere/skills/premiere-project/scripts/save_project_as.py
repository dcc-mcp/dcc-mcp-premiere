"""Save a verified Premiere project copy."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import save_project_as
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere project copy saved.", save_project_as, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
