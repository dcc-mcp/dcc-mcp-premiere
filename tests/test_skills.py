import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS = (
    Path(__file__).parents[1]
    / "src"
    / "dcc_mcp_premiere"
    / "skills"
    / "premiere-project"
    / "scripts"
)


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_skills_use_typed_premiere_facade():
    sequence = SimpleNamespace(name="Main")
    project = SimpleNamespace(
        name="Demo", active_sequence=sequence, sequences=[sequence], save=mock.Mock()
    )
    for name, expected in (
        ("inspect_project", {"project_name": "Demo", "active_sequence": "Main"}),
        ("list_sequences", {"sequences": [{"name": "Main"}], "sequence_count": 1}),
        ("save_project", {"saved": True}),
    ):
        module = load_script(name)
        with mock.patch.object(module, "Premiere", return_value=SimpleNamespace(project=project)):
            assert getattr(module, name)() == expected
    project.save.assert_called_once()
