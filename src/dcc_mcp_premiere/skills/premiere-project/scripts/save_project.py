from adobe.core.errors import HostScriptError
from adobe.dcc_mcp import action_result
from adobe.premiere import Premiere
from dcc_mcp_core.skill import skill_entry


def save_project():
    project = Premiere().project
    if project is None:
        raise HostScriptError("Premiere has no active project")
    project.save()
    return {"saved": True}


@skill_entry
def main(**_kwargs):
    return action_result("Premiere project saved.", save_project)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
