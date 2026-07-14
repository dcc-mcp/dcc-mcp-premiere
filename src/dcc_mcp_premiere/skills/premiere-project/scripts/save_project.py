from dcc_mcp_core.skill import skill_entry, skill_success

from dcc_mcp_premiere.bridge import call_bridge


@skill_entry
def main(**_kwargs):
    return skill_success(
        "Premiere project saved.", **call_bridge("DCC_MCP_PREMIERE", "save_project", {})
    )


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
