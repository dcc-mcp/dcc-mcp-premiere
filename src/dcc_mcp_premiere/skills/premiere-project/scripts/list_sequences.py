from adobe.core.errors import HostScriptError
from adobe.dcc_mcp import action_result
from adobe.premiere import Premiere
from dcc_mcp_core.skill import skill_entry


def list_sequences():
    project = Premiere().project
    if project is None:
        raise HostScriptError("Premiere has no active project")
    sequences = [{"name": sequence.name} for sequence in project.sequences]
    return {"sequences": sequences, "sequence_count": len(sequences)}


@skill_entry
def main(**_kwargs):
    return action_result("Premiere sequences listed.", list_sequences)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
