"""List a bounded page of Premiere sequences."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import list_sequences
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere sequences listed.", list_sequences, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
