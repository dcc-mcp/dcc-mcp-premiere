from unittest import mock

from adobe.runtime import BrokerHandle

from dcc_mcp_premiere.config import PremiereConfig
from dcc_mcp_premiere.runtime import PremiereStatus
from dcc_mcp_premiere.server import PremiereMcpServer


def test_server_uses_host_rpc_for_readiness_and_owned_broker_lifecycle():
    broker = BrokerHandle("http://127.0.0.1:47391", "token")
    broker.stop = mock.Mock()
    broker_factory = mock.Mock(return_value=broker)
    readiness_probe = mock.Mock(
        return_value=PremiereStatus(True, version="25.6.0", target="default")
    )
    server = PremiereMcpServer(
        gateway_port=0,
        config=PremiereConfig(
            token="token",
            broker_path="C:/tools/adobepy.exe",
            timeout=1.0,
            poll_interval=60.0,
        ),
        broker_factory=broker_factory,
        readiness_probe=readiness_probe,
    )
    server.update_gateway_metadata = mock.Mock()

    with mock.patch("dcc_mcp_premiere.server.DccServerBase.start", return_value=object()):
        server.start(install_atexit_hook=False)

    assert server.bridge_status.ready is True
    assert server._readiness.probe.report()["dcc"] is True
    server.update_gateway_metadata.assert_called_once_with(scene="bridge_ready", version="25.6.0")
    broker_factory.assert_called_once_with(
        broker_url=None,
        token="token",
        broker_path="C:/tools/adobepy.exe",
        timeout=1.0,
    )

    with mock.patch("dcc_mcp_premiere.server.DccServerBase.stop"):
        server.stop()
    broker.stop.assert_called_once_with()


def test_server_rolls_back_broker_when_base_start_fails():
    broker = BrokerHandle("http://127.0.0.1:47391", "token")
    broker.stop = mock.Mock()
    server = PremiereMcpServer(
        gateway_port=0,
        config=PremiereConfig(token="token", timeout=1.0, poll_interval=60.0),
        broker_factory=mock.Mock(return_value=broker),
        readiness_probe=mock.Mock(return_value=PremiereStatus(False, "offline")),
    )

    with mock.patch(
        "dcc_mcp_premiere.server.DccServerBase.start", side_effect=RuntimeError("bind failed")
    ):
        try:
            server.start(install_atexit_hook=False)
        except RuntimeError as error:
            assert str(error) == "bind failed"
        else:
            raise AssertionError("start should have failed")

    broker.stop.assert_called_once_with()
    assert server.broker is None


def test_server_refuses_implicit_development_token():
    broker_factory = mock.Mock()
    server = PremiereMcpServer(
        gateway_port=0,
        config=PremiereConfig(token=None, timeout=1.0, poll_interval=60.0),
        broker_factory=broker_factory,
    )

    with mock.patch("dcc_mcp_premiere.server.DccServerBase.start"):
        try:
            server.start(install_atexit_hook=False)
        except RuntimeError as error:
            assert str(error) == "ADOBEPY_TOKEN must be configured in the environment"
        else:
            raise AssertionError("server should fail closed without an operator token")

    broker_factory.assert_not_called()
