import importlib
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "deploy" / "runpod"))
    return importlib.import_module("worker")


@pytest.fixture
def job():
    return json.loads((Path(__file__).resolve().parents[2] / "deploy/runpod/test_input.json").read_text())


def test_worker_repeated_requests_and_invalid_then_valid(worker, job):
    seen = []

    def respond(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        data = json.loads(request.content)
        assert data["keep_alive"] == "10m"
        assert data["stream"] is False and data["think"] is False
        seen.append(data)
        return httpx.Response(200, json={"message": {"content": "worker ready"}, "done": True, "done_reason": "stop"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError, match="Invalid inference input"):
            worker.handle_job({"input": {"messages": []}}, client=client, model="llama3.1:8b")
        for _ in range(2):
            assert worker.handle_job(job, client=client, model="llama3.1:8b")["message"]["content"] == "worker ready"
    assert len(seen) == 2
    assert "keep_alive" not in job["input"]


@pytest.mark.parametrize("change", [
    {"model": "another-model"}, {"messages": []},
    {"messages": [{"role": "tool", "content": "x"}]},
    {"messages": [{"role": "user", "content": "x" * 60001}]},
    {"messages": [{"role": "user", "content": "x" * 50001}] * 2},
    {"stream": True}, {"think": True}, {"keep_alive": "0"},
    {"options": {"num_predict": -1}}, {"options": {"num_predict": 8193}},
    {"options": {"num_ctx": 32769}}, {"options": {"num_gpu": 0}},
    {"options": {"temperature": float("inf")}},
])
def test_worker_rejects_invalid_or_unbounded_requests_before_inference(worker, job, change):
    def unexpected(request):
        pytest.fail("Invalid input must not reach Ollama")
    job["input"].update(change)
    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ValueError):
            worker.handle_job(job, client=client, model="llama3.1:8b")


@pytest.mark.parametrize("status, body", [(500, {"error": "private input"}), (200, []),
                                          (200, {"message": None}), (200, {"message": {"content": ""}})])
def test_worker_failure_is_sanitized(worker, job, status, body):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))) as client:
        with pytest.raises(RuntimeError) as error:
            worker.handle_job(job, client=client, model="llama3.1:8b")
    assert "private input" not in str(error.value)


def test_worker_preserves_truncation_reason_for_analysis_validation(worker, job):
    body = {"message": {"content": "partial JSON"}, "done_reason": "length"}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        assert worker.handle_job(deepcopy(job), client=client, model="llama3.1:8b")["done_reason"] == "length"
