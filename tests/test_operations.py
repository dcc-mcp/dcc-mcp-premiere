from pathlib import Path
from types import SimpleNamespace

import pytest

from dcc_mcp_premiere import operations


class FakeItem:
    def __init__(
        self,
        identifier,
        name,
        *,
        item_type="CLIP",
        is_bin=False,
        media_path=None,
        children=None,
        parent_id=None,
    ):
        self.id = identifier
        self.name = name
        self.item_type = item_type
        self.path = None
        self.media_path = media_path
        self.tree_path = f"/Root/{name}"
        self.parent_id = parent_id
        self.children = list(children or [])
        self.is_bin = is_bin
        self.is_clip = not is_bin
        self.is_sequence = False
        self.can_proxy = True
        self.has_proxy = False
        self.is_offline = False
        self.typename = "ProjectItem"

    @property
    def child_count(self):
        return len(self.children)

    def create_bin(self, name, **_kwargs):
        created = FakeItem(
            f"bin-{len(self.children) + 1}",
            name,
            item_type="BIN",
            is_bin=True,
            parent_id=self.id,
        )
        self.children.append(created)
        return created


class FakeClip:
    def __init__(self, item):
        self.id = "clip-1"
        self.name = item.name
        self.project_item_id = item.id
        self.media_path = item.media_path
        self.start = 0.0
        self.end = 1.0
        self.in_point = 0.0
        self.out_point = 1.0
        self.duration = 1.0
        self.is_enabled = True
        self.is_selected = True
        self.typename = "TrackItem"


class FakeTrack:
    def __init__(self, index, media_type, clips=None):
        self.id = f"{media_type}-{index}"
        self.name = f"{media_type.title()} {index + 1}"
        self.index = index
        self.media_type = media_type
        self.is_locked = False
        self.is_muted = False
        self.is_targeted = True
        self.clips = list(clips or [])
        self.typename = "Track"


def fake_marker(identifier="marker-1", name="Review"):
    return SimpleNamespace(
        id=identifier,
        name=name,
        comments="",
        start=0.0,
        end=1.0,
        duration=1.0,
        marker_type="Comment",
        typename="Marker",
    )


def fake_job(path, *, status="queued"):
    return SimpleNamespace(
        id="job-1",
        job_id="job-1",
        status=status,
        output_path=str(path),
        preset_path=None,
        source_id="seq-1",
        source_name="Main",
        export_type="QUEUE_TO_AME",
        remove_on_completion=True,
        started=True,
        typename="ExportJob",
    )


class FakeSequence:
    def __init__(self, identifier="seq-1", name="Main"):
        self.id = identifier
        self.sequence_id = identifier
        self.name = name
        self.duration = 10.0
        self.timebase = 1 / 24
        self.typename = "Sequence"
        self.video_tracks = [FakeTrack(0, "video")]
        self.audio_tracks = [FakeTrack(0, "audio")]
        self.markers = [fake_marker()]
        self.selected_clips = []
        self.edits = []

    def insert_project_item(self, item, **kwargs):
        clip = FakeClip(item)
        self.video_tracks[0].clips.append(clip)
        self.selected_clips = [clip]
        self.edits.append(("insert", item.id, kwargs))
        return {"inserted": True}

    def overwrite_project_item(self, item, **kwargs):
        self.edits.append(("overwrite", item.id, kwargs))
        return {"overwritten": True}

    def create_marker(self, name, *, start, comments, duration, marker_type, **_kwargs):
        marker = fake_marker(f"marker-{len(self.markers) + 1}", name)
        marker.start = start
        marker.comments = comments
        marker.duration = duration
        marker.marker_type = marker_type
        self.markers.append(marker)
        return marker

    def export(self, path, **_kwargs):
        return fake_job(path)

    def export_frame(self, path, **_kwargs):
        Path(path).write_bytes(b"fake-png")
        return fake_job(path, status="completed")


class FakeProject:
    def __init__(self, root, sequence, path=None):
        self.id = "project-1"
        self.guid = "guid-1"
        self.name = "Demo"
        self.path = str(path) if path else None
        self.root_item = root
        self.sequences = [sequence]
        self.active_sequence = sequence
        self.selected_items = list(root.children[:1])

    @property
    def item_count(self):
        return len(self.root_item.children)

    def save(self, **_kwargs):
        if self.path:
            Path(self.path).write_bytes(b"fake-project")
        return self

    def save_as(self, path, **_kwargs):
        Path(path).write_bytes(b"fake-project-copy")
        self.path = path
        return self

    def create_sequence(self, name, **_kwargs):
        created = FakeSequence(f"seq-{len(self.sequences) + 1}", name)
        self.sequences.append(created)
        self.active_sequence = created
        return created

    def import_files(self, paths, *, target_bin, **_kwargs):
        imported = []
        for path in paths:
            item = FakeItem(
                f"item-{len(target_bin.children) + 1}", Path(path).name, media_path=path
            )
            target_bin.children.append(item)
            imported.append(item)
        return imported


class FakeApp:
    def __init__(self, project):
        self.version = "25.6.0"
        self.project = project
        self.encoder = SimpleNamespace(
            is_ame_installed=True,
            presets=[
                SimpleNamespace(
                    name="H.264",
                    path="/presets/h264.epr",
                    format="H.264",
                    extension="mp4",
                    typename="EncoderPreset",
                )
            ],
            get_export_file_extension=lambda _sequence, _preset: "mp4",
        )

    @property
    def active_sequence(self):
        return self.project.active_sequence


@pytest.fixture
def facade(tmp_path):
    item = FakeItem("item-1", "shot.mp4", media_path=str(tmp_path / "shot.mp4"))
    root = FakeItem("root", "Root", item_type="ROOT", is_bin=True, children=[item])
    sequence = FakeSequence()
    project = FakeProject(root, sequence, tmp_path / "active.prproj")
    app = FakeApp(project)
    return app, lambda: app


def test_read_operations_return_bounded_typed_data(facade):
    app, factory = facade

    assert operations.get_status(app_factory=factory)["version"] == "25.6.0"
    assert operations.inspect_project(app_factory=factory)["selected_count"] == 1
    assert operations.list_sequences(limit=1, app_factory=factory)["total"] == 1
    inspected = operations.inspect_sequence(clip_limit=5, app_factory=factory)
    assert inspected["sequence"]["id"] == "seq-1"
    assert len(inspected["video_tracks"]) == 1
    listed = operations.list_project_items(query="shot", app_factory=factory)
    assert listed["items"][0]["id"] == "item-1"

    app.project.active_sequence.insert_project_item(app.project.root_item.children[0])
    selected = operations.list_selected_clips(app_factory=factory)
    assert selected["clips"][0]["project_item_id"] == "item-1"


def test_project_and_timeline_authoring_use_typed_facade(tmp_path, monkeypatch, facade):
    app, factory = facade
    media = tmp_path / "new-shot.mov"
    media.write_bytes(b"media")
    preset = tmp_path / "sequence.sqpreset"
    preset.write_text("preset", encoding="utf-8")
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_INPUT_ROOTS", str(tmp_path))
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_PRESET_ROOTS", str(tmp_path))

    created_bin = operations.create_bin(name="DCC-MCP", app_factory=factory)["bin"]
    imported = operations.import_media(
        paths=[str(media)], target_bin=created_bin["id"], app_factory=factory
    )
    created_sequence = operations.create_sequence(
        name="DCC-MCP Sequence", preset_path=str(preset), app_factory=factory
    )["sequence"]
    edited = operations.insert_project_item(
        project_item=imported["items"][0]["id"],
        sequence=created_sequence["id"],
        time=1.25,
        video_track=0,
        audio_track=0,
        app_factory=factory,
    )
    overwritten = operations.overwrite_project_item(
        project_item=imported["items"][0]["id"],
        sequence=created_sequence["id"],
        time=2,
        app_factory=factory,
    )
    marker = operations.create_marker(
        name="Review",
        start=3,
        sequence=created_sequence["id"],
        comments="Check grade",
        duration=1,
        marker_type="Comment",
        app_factory=factory,
    )

    assert edited["mode"] == "insert"
    assert overwritten["mode"] == "overwrite"
    assert marker["marker"]["name"] == "Review"
    assert app.project.active_sequence.edits[0][2]["time"] == 1.25


def test_verified_save_frame_and_queued_export(tmp_path, monkeypatch, facade):
    _app, factory = facade
    preset = tmp_path / "h264.epr"
    preset.write_text("preset", encoding="utf-8")
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_OUTPUT_ROOTS", str(tmp_path))
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_PRESET_ROOTS", str(tmp_path))

    project = operations.save_project_as(path=str(tmp_path / "copy.prproj"), app_factory=factory)
    frame = operations.export_frame(
        output_path=str(tmp_path / "frame.png"), time=0, app_factory=factory
    )
    queued = operations.queue_sequence_export(
        output_path=str(tmp_path / "edit.mp4"),
        preset_path=str(preset),
        app_factory=factory,
    )

    assert project["file"]["bytes"] == len(b"fake-project-copy")
    assert len(project["file"]["sha256"]) == 64
    assert frame["file"]["bytes"] == len(b"fake-png")
    assert queued["queued"] is True
    assert queued["output_exists_after_queue"] is False
    assert queued["output_preexisted"] is False


def test_paths_overwrite_and_dimensions_are_rejected(tmp_path, monkeypatch, facade):
    _app, factory = facade
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.mov"
    outside.write_bytes(b"outside")
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_INPUT_ROOTS", str(allowed))
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_OUTPUT_ROOTS", str(allowed))

    with pytest.raises(operations.PremiereOperationError, match="outside"):
        operations.import_media(paths=[str(outside)], app_factory=factory)
    with pytest.raises(operations.PremiereOperationError, match="provided together"):
        operations.export_frame(
            output_path=str(allowed / "frame.png"), width=1920, time=0, app_factory=factory
        )
    existing = allowed / "copy.prproj"
    existing.write_bytes(b"do-not-replace")
    with pytest.raises(operations.PremiereOperationError, match="already exists"):
        operations.save_project_as(path=str(existing), app_factory=factory)
    assert existing.read_bytes() == b"do-not-replace"

    facade[0].project.save_as = lambda _path, **_kwargs: facade[0].project
    with pytest.raises(RuntimeError, match="did not change"):
        operations.save_project_as(path=str(existing), overwrite=True, app_factory=factory)


def test_encoder_must_report_a_safe_output_extension(tmp_path, monkeypatch, facade):
    app, factory = facade
    preset = tmp_path / "unsafe.epr"
    preset.write_text("preset", encoding="utf-8")
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_OUTPUT_ROOTS", str(tmp_path))
    monkeypatch.setenv("DCC_MCP_PREMIERE_ALLOWED_PRESET_ROOTS", str(tmp_path))
    app.encoder.get_export_file_extension = lambda _sequence, _preset: None

    with pytest.raises(operations.PremiereOperationError, match="safe output extension"):
        operations.queue_sequence_export(
            output_path=str(tmp_path / "arbitrary.output"),
            preset_path=str(preset),
            app_factory=factory,
        )


def test_list_validation_and_missing_identity_are_stable(facade):
    _app, factory = facade
    with pytest.raises(operations.PremiereOperationError, match="limit"):
        operations.list_sequences(limit=0, app_factory=factory)
    with pytest.raises(operations.PremiereOperationError, match="Sequence not found"):
        operations.inspect_sequence(sequence="missing", app_factory=factory)
    with pytest.raises(operations.PremiereOperationError, match="Project item not found"):
        operations.insert_project_item(project_item="missing", app_factory=factory)
