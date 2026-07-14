from adobe.core.errors import HostScriptError
from adobe.dcc_mcp import action_result
from adobe.premiere import Premiere
from dcc_mcp_core.skill import skill_entry


def inspect_project():
    project = Premiere().project
    if project is None:
        raise HostScriptError("Premiere has no active project")
    sequence = project.active_sequence
    return {"project_name": project.name, "active_sequence": sequence.name if sequence else None}


@skill_entry
def main(**_kwargs):
    return action_result("Premiere project inspected.", inspect_project)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
