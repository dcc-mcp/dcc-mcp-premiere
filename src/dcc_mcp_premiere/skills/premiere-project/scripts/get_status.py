"""Return typed Premiere bridge and host status."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import get_status
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**_kwargs):
    return invoke("Premiere status returned.", get_status)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
