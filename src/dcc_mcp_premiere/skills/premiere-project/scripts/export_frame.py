"""Export and verify one Premiere sequence frame."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import export_frame
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere frame exported.", export_frame, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
