import importlib.util
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest


@pytest.fixture
def runtime():
    # Load under a distinct name; do not collide with app.runtime or other modules.
    path = Path(__file__).resolve().parents[2] / "deploy/runpod/runtime.py"
    spec = importlib.util.spec_from_file_location("runpod_ollama_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_process(monkeypatch, runtime, *, ready=True, exited=False):
    process = Mock()
    process.poll.return_value = 1 if exited else None
    popen = Mock(return_value=process)
    monkeypatch.setattr(runtime.subprocess, "Popen", popen)
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    if ready:
        client.get.return_value = httpx.Response(200, json={"models": []})
    else:
        client.get.side_effect = httpx.ConnectError("Not ready")
    monkeypatch.setattr(runtime.httpx, "Client", Mock(return_value=client))
    return process, popen


def test_worker_starts_private_ollama_and_cleans_up_after_handler_failure(runtime, monkeypatch):
    process, popen = setup_process(monkeypatch, runtime)
    with pytest.raises(ValueError, match="handler failed"):
        with runtime.ollama_server():
            assert popen.call_args.kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
            assert popen.call_args.args[0] == ["ollama", "serve"]
            raise ValueError("handler failed")
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=10)


def test_worker_fails_when_ollama_exits_during_startup(runtime, monkeypatch):
    process, _ = setup_process(monkeypatch, runtime, exited=True)
    with pytest.raises(RuntimeError, match="exited"):
        with runtime.ollama_server():
            pytest.fail("A dead Ollama process must never accept jobs")
    process.terminate.assert_called_once()


def test_readiness_deadline_kills_unresponsive_child(runtime, monkeypatch):
    process, _ = setup_process(monkeypatch, runtime, ready=False)
    monkeypatch.setattr(runtime.time, "monotonic", Mock(side_effect=[0, 61]))
    process.wait.side_effect = [runtime.subprocess.TimeoutExpired("ollama", 10), None]
    with pytest.raises(RuntimeError, match="60 seconds"):
        with runtime.ollama_server():
            pytest.fail("A worker must not start without Ollama readiness")
    process.kill.assert_called_once()
    assert process.wait.call_count == 2
