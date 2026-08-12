import re
from pathlib import Path

from dcc_mcp_core import validate_skill

SKILL = Path(__file__).parents[1] / "src" / "dcc_mcp_premiere" / "skills" / "premiere-project"


def test_skill_is_valid_and_exposes_complete_bounded_contract():
    report = validate_skill(str(SKILL))
    assert report.is_clean, report.issues

    text = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    names = set(re.findall(r"^  - name: ([a-z0-9_]+)$", text, flags=re.MULTILINE))
    assert len(names) == 17
    assert names == {
        "get_status",
        "inspect_project",
        "list_sequences",
        "inspect_sequence",
        "list_project_items",
        "list_selected_clips",
        "create_bin",
        "import_media",
        "create_sequence",
        "insert_project_item",
        "overwrite_project_item",
        "create_marker",
        "save_project",
        "save_project_as",
        "list_encoder_presets",
        "queue_sequence_export",
        "export_frame",
    }
    assert text.count("additionalProperties: false") == 17
    assert text.count("affinity: any") == 17


def test_skill_scripts_are_typed_entry_points_without_raw_execution():
    manifest = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    combined = ""
    sources = re.findall(r"^    source_file: (.+)$", manifest, flags=re.MULTILINE)
    assert len(sources) == 17
    for relative_path in sources:
        source = SKILL / relative_path
        assert source.is_file()
        text = source.read_text(encoding="utf-8")
        assert "@skill_entry" in text
        assert "dcc_mcp_premiere.operations" in text
        combined += text
    lowered = combined.casefold()
    assert "evaljs" not in lowered
    assert "subprocess" not in lowered
    assert "exec(" not in lowered
