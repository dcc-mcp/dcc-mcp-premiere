"""Production lifecycle for the adobepy-backed Premiere adapter."""

from __future__ import annotations

import logging
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Optional

from adobe.runtime import BrokerHandle, ensure_broker
from dcc_mcp_core import DccServerOptions
from dcc_mcp_core.readiness import AdapterReadinessBinder
from dcc_mcp_core.server_base import DccServerBase

from .__version__ import __version__
from .capabilities import premiere_capabilities
from .config import PremiereConfig
from .context import collect_context
from .runtime import PremiereStatus, probe_premiere

logger = logging.getLogger(__name__)
DEFAULT_PORT = 0
_server: Optional["PremiereMcpServer"] = None
_server_lock = threading.Lock()


class PremiereMcpServer(DccServerBase):
    """Server that reports ready only after a complete bridge and real host RPC."""

    def __init__(
        self,
        port: int | None = None,
        *,
        gateway_port: int | None = None,
        config: PremiereConfig | None = None,
        broker_factory: Callable[..., BrokerHandle] = ensure_broker,
        readiness_probe: Callable[..., PremiereStatus] = probe_premiere,
    ) -> None:
        self.adapter_config = config or PremiereConfig.from_env()
        self.broker: BrokerHandle | None = None
        self._broker_factory = broker_factory
        self._readiness_probe = readiness_probe
        self._bridge_status = PremiereStatus(False, "bridge has not been checked")
        self._watch_stop = threading.Event()
        self._watch_thread: threading.Thread | None = None
        options = DccServerOptions.from_env(
            "premiere",
            Path(__file__).resolve().parent / "skills",
            port=port,
            gateway_port=gateway_port,
            server_name="dcc-mcp-premiere",
            server_version=__version__,
            instance_type="gui",
        )
        super().__init__(options=options)
        self._readiness = AdapterReadinessBinder(self)
        self._readiness.mark_dispatcher_ready(
            True,
            host_execution_bridge_ready=True,
            main_thread_executor_ready=True,
            dcc_ready=False,
        )
        self.set_context_snapshot_provider(self._context_snapshot)

    @property
    def bridge_status(self) -> PremiereStatus:
        return self._bridge_status

    def _active_connection(self) -> tuple[str | None, str | None]:
        if self.broker is not None:
            return self.broker.url, self.broker.token
        return self.adapter_config.broker_url, self.adapter_config.token

    def _sample_bridge(self) -> PremiereStatus:
        broker_url, token = self._active_connection()
        status = self._readiness_probe(
            broker_url=broker_url,
            token=token,
            target=self.adapter_config.target,
            timeout=self.adapter_config.timeout,
        )
        changed = status != self._bridge_status
        self._bridge_status = status
        self._readiness.probe.set_dcc_ready(status.ready)
        if changed and self.is_running:
            self.update_gateway_metadata(
                scene="bridge_ready" if status.ready else "bridge_waiting",
                version=status.version or "",
            )
        return status

    def _watch_bridge(self) -> None:
        while not self._watch_stop.wait(self.adapter_config.poll_interval):
            try:
                self._sample_bridge()
            except Exception as error:
                logger.warning("Premiere readiness check failed: %s", error)
                self._readiness.probe.set_dcc_ready(False)

    def _start_watchdog(self) -> None:
        if self._watch_thread is not None and self._watch_thread.is_alive():
            return
        self._watch_stop.clear()
        self._watch_thread = threading.Thread(
            target=self._watch_bridge,
            name="premiere-bridge-watchdog",
            daemon=True,
        )
        self._watch_thread.start()

    def _stop_watchdog(self) -> None:
        self._watch_stop.set()
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=max(1.0, self.adapter_config.poll_interval + 0.5))
            self._watch_thread = None

    def _context_snapshot(self):
        broker_url, token = self._active_connection()
        return collect_context(
            broker_url=broker_url,
            token=token,
            target=self.adapter_config.target,
            timeout=self.adapter_config.timeout,
        )

    def get_capabilities(self):
        return premiere_capabilities()

    def start(self, *, install_atexit_hook: bool = True) -> Any:
        if self.is_running:
            return super().start(install_atexit_hook=install_atexit_hook)
        if not self.adapter_config.token:
            raise RuntimeError("ADOBEPY_TOKEN must be configured in the environment")
        self.broker = self._broker_factory(
            broker_url=self.adapter_config.broker_url,
            token=self.adapter_config.token,
            broker_path=self.adapter_config.broker_path,
            timeout=self.adapter_config.timeout,
        )
        try:
            status = self._sample_bridge()
            handle = super().start(install_atexit_hook=install_atexit_hook)
            self.update_gateway_metadata(
                scene="bridge_ready" if status.ready else "bridge_waiting",
                version=status.version or "",
            )
            self._start_watchdog()
            return handle
        except Exception:
            self._stop_watchdog()
            self.broker.stop()
            self.broker = None
            raise

    def stop(self) -> None:
        self._stop_watchdog()
        try:
            super().stop()
        finally:
            if self.broker is not None:
                self.broker.stop()
                self.broker = None


def start_server(
    port: int | None = None,
    *,
    broker_url: str | None = None,
    gateway_port: int | None = None,
    extra_skill_paths: list[str] | None = None,
    include_bundled: bool = True,
) -> PremiereMcpServer:
    global _server
    with _server_lock:
        if _server is None or not _server.is_running:
            config = PremiereConfig.from_env()
            if broker_url is not None:
                config = PremiereConfig(
                    broker_url=broker_url,
                    token=config.token,
                    broker_path=config.broker_path,
                    target=config.target,
                    timeout=config.timeout,
                    poll_interval=config.poll_interval,
                )
            candidate = PremiereMcpServer(port, gateway_port=gateway_port, config=config)
            try:
                candidate.run_registration(
                    extra_skill_paths=extra_skill_paths,
                    include_bundled=include_bundled,
                )
                candidate.start()
            except Exception:
                with suppress(Exception):
                    candidate.stop()
                raise
            _server = candidate
        return _server


def stop_server() -> None:
    global _server
    with _server_lock:
        try:
            if _server is not None:
                _server.stop()
        finally:
            _server = None


__all__ = ["PremiereMcpServer", "start_server", "stop_server"]
