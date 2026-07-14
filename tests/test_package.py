from pathlib import Path

from dcc_mcp_premiere import __version__


def test_version_metadata_is_synchronized():
    root = Path(__file__).parents[1]
    assert f'version = "{__version__}"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert f'".": "{__version__}"' in (root / ".release-please-manifest.json").read_text(
        encoding="utf-8"
    )


def test_uxp_panel_is_packaged_with_source():
    panel = Path(__file__).parents[1] / "src" / "dcc_mcp_premiere" / "premiere_uxp"
    assert (panel / "manifest.json").is_file()
    assert (panel / "index.js").is_file()
