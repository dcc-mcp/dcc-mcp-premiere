"""List bounded Premiere encoder presets."""

from dcc_mcp_core.skill import skill_entry

from dcc_mcp_premiere.operations import list_encoder_presets
from dcc_mcp_premiere.skill_support import invoke


@skill_entry
def main(**kwargs):
    return invoke("Premiere encoder presets listed.", list_encoder_presets, **kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
