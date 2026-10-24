from types import SimpleNamespace

from dcc_mcp_premiere.context import collect_context


def test_context_omits_project_and_media_paths():
    project = SimpleNamespace(
        name="Demo",
        path="C:/private/project.prproj",
        item_count=4,
        sequences=[SimpleNamespace(name="Main")],
    )
    sequence = project.sequences[0]
    app = SimpleNamespace(
        version="25.6.0",
        project=project,
        active_sequence=sequence,
    )
    captured = {}

    def client_factory(**kwargs):
        captured.update(kwargs)
        return object()

    snapshot = collect_context(
        broker_url="http://127.0.0.1:47391",
        token="secret",
        target="edit",
        timeout=1.0,
        client_factory=client_factory,
        app_factory=lambda **_kwargs: app,
    )

    assert snapshot.document == {"name": "Demo"}
    assert snapshot.active_object == {"name": "Main"}
    assert snapshot.counts == {"project_items": 4, "sequences": 1}
    assert "path" not in str(snapshot)
    assert captured["token"] == "secret"
