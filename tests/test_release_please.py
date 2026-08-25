import json
import re
from pathlib import Path

from dcc_mcp_core import yaml_loads

ROOT = Path(__file__).resolve().parents[1]
VERSION_SOURCES = {
    "src/dcc_mcp_premiere/__version__.py": 1,
    "src/dcc_mcp_premiere/skills/premiere-project/SKILL.md": 1,
    "install.md": 3,
}
PINNED_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "googleapis/release-please-action": "45996ed1f6d02564a971a2fa1b5860e934307cf7",
    "pypa/gh-action-pypi-publish": "dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
}


def test_release_please_tracks_every_version_source() -> None:
    config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    extra_files = config["packages"]["."]["extra-files"]
    configured_paths = {entry if isinstance(entry, str) else entry["path"] for entry in extra_files}
    assert VERSION_SOURCES.keys() <= configured_paths

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert project_version is not None
    for relative_path, expected_markers in VERSION_SOURCES.items():
        lines = (ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        marker_lines = [line for line in lines if "x-release-please-version" in line]
        assert len(marker_lines) == expected_markers, relative_path
        assert project_version.group(1) in marker_lines[0], relative_path


def test_install_support_matrix_matches_current_release() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert project_version is not None

    lines = (ROOT / "install.md").read_text(encoding="utf-8").splitlines()
    supported_rows = [line for line in lines if "x-release-please-version" in line]

    assert len(supported_rows) == 3
    assert all(f"| {project_version.group(1)} " in line for line in supported_rows)


def test_release_workflow_reuses_one_immutable_distribution_artifact() -> None:
    workflow = yaml_loads((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {}
    assert jobs["build"]["needs"] == "release-please"
    assert jobs["publish-pypi"]["needs"] == ["release-please", "build"]
    assert jobs["attach-github-release"]["needs"] == [
        "release-please",
        "build",
        "publish-pypi",
    ]

    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["publish-pypi"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }
    assert jobs["attach-github-release"]["permissions"] == {"contents": "write"}

    all_steps = [step for job in jobs.values() for step in job.get("steps", [])]
    build_steps = [step for step in all_steps if step.get("run") == "python -m build"]
    assert len(build_steps) == 1
    assert build_steps[0] in jobs["build"]["steps"]

    upload_step = next(
        step
        for step in jobs["build"]["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload_step["with"] == {
        "name": "release-distributions",
        "path": "dist/",
        "if-no-files-found": "error",
    }
    build_job_steps = jobs["build"]["steps"]
    assert build_job_steps.index(build_steps[0]) < build_job_steps.index(upload_step)

    download_steps = []
    for job_name in ("publish-pypi", "attach-github-release"):
        step = next(
            step
            for step in jobs[job_name]["steps"]
            if step.get("uses", "").startswith("actions/download-artifact@")
        )
        assert step["with"] == {"name": "release-distributions", "path": "dist/"}
        download_steps.append(step)
    assert len(download_steps) == 2

    tag_expression = "${{ needs.release-please.outputs.tag_name }}"
    checkout_step = next(
        step
        for step in jobs["build"]["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout_step["with"]["ref"] == tag_expression

    publish_step = next(
        step
        for step in jobs["publish-pypi"]["steps"]
        if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
    )
    assert publish_step["with"]["packages-dir"] == "dist/"
    assert jobs["publish-pypi"]["steps"].index(download_steps[0]) < jobs["publish-pypi"][
        "steps"
    ].index(publish_step)

    attach_job = jobs["attach-github-release"]
    assert attach_job["env"]["TAG_NAME"] == tag_expression
    attach_command = next(step["run"] for step in attach_job["steps"] if "run" in step)
    assert attach_command == 'gh release upload "$TAG_NAME" dist/* --repo "$GITHUB_REPOSITORY"'
    assert attach_job["steps"].index(download_steps[1]) < next(
        index for index, step in enumerate(attach_job["steps"]) if "run" in step
    )

    pinned_action = re.compile(r"^[^@]+@[0-9a-f]{40}$")
    for step in all_steps:
        if "uses" in step:
            assert pinned_action.fullmatch(step["uses"]), step["uses"]
            action, revision = step["uses"].split("@", 1)
            assert revision == PINNED_ACTIONS[action]
