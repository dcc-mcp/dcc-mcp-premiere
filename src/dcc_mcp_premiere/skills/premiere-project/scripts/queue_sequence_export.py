"""Queue a safe Premiere sequence export in Adobe Media Encoder."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import queue_sequence_export
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere sequence export queued.", queue_sequence_export, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
