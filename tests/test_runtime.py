from dcc_mcp_premiere.runtime import REQUIRED_METHODS, probe_premiere


def complete_capabilities():
    return {
        "host": "premiere",
        "methods": {namespace: list(methods) for namespace, methods in REQUIRED_METHODS.items()},
    }


class FakeClient:
    def __init__(self, sessions):
        self.sessions = sessions

    def capabilities(self):
        return self.sessions


def test_probe_requires_matching_complete_session_and_real_version_rpc():
    client = FakeClient([{"target": "edit", "capabilities": complete_capabilities()}])
    captured = []

    def app_factory(*, client):
        captured.append(client)
        return type("App", (), {"version": "25.6.0"})()

    status = probe_premiere(client=client, target="edit", app_factory=app_factory)

    assert status.ready is True
    assert status.version == "25.6.0"
    assert status.target == "edit"
    assert captured == [client]


def test_probe_reports_missing_session_and_methods_without_version_rpc():
    empty = probe_premiere(client=FakeClient([]), app_factory=lambda **_kwargs: None)
    assert empty.ready is False
    assert "not connected" in empty.reason

    capabilities = complete_capabilities()
    capabilities["methods"]["project"].remove("saveAs")
    client = FakeClient([{"target": "default", "capabilities": capabilities}])
    missing = probe_premiere(client=client, app_factory=lambda **_kwargs: None)
    assert missing.ready is False
    assert "project.saveAs" in missing.reason


def test_probe_contains_no_raw_method_and_contains_all_operation_namespaces():
    flattened = {
        f"{namespace}.{method}"
        for namespace, methods in REQUIRED_METHODS.items()
        for method in methods
    }
    assert "raw.evalJs" not in flattened
    assert {"project", "projectItem", "sequence", "encoder", "export"} <= set(REQUIRED_METHODS)
