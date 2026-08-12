"""Create a typed Premiere sequence marker."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import create_marker
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere marker created.", create_marker, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
