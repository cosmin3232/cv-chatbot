import asyncio
import importlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import inference
from app.config import Settings
from app.conversation_store import ConversationStore
from app.main import create_app

CHAT = {"conversationId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "messageId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "prompt": "What skills does the candidate have?"}
MODEL_OUTPUT = {"message": {"content": "Python (CV, page 1)."}, "done": True, "done_reason": "stop"}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "POLL_INTERVAL_SECONDS", 0.001)
    profile = tmp_path / "knowledge.md"
    profile.write_text("## CV, page 1\nDeveloped Python APIs with FastAPI.", encoding="utf-8")
    return Settings(_env_file=None, knowledge_path=profile, inference_provider="runpod",
                    runpod_endpoint_id="endpoint-123", runpod_api_key="test-secret", ollama_num_gpu=0)


def test_runpod_chat_polls_preserves_grounding_and_saves_reply(settings):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert request.url.host == "api.runpod.ai"
        if request.url.path.endswith("/run"):
            body = json.loads(request.content)
            data = body["input"]
            assert data["model"] == settings.ollama_model
            assert data["stream"] is False and data["think"] is False
            assert "num_gpu" not in data["options"]  # Local CPU setting cannot disable remote GPUs.
            assert "Never invent" in data["messages"][0]["content"]
            assert "Developed Python" in data["messages"][1]["content"]
            assert body["policy"] == {"executionTimeout": 300000, "ttl": 310000}
            return httpx.Response(200, json={"id": "job-123", "status": "IN_QUEUE"})
        if len(calls) == 2:
            return httpx.Response(200, json={"id": "job-123", "status": "IN_PROGRESS"})
        return httpx.Response(200, json={"id": "job-123", "status": "COMPLETED", "output": MODEL_OUTPUT})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        assert client.get("/health").json()["inferenceProvider"] == "runpod"
        assert not calls  # Health checks must not wake a billed worker.
        response = client.post("/api/chat", json=CHAT)
        assert response.status_code == 200
        assert response.json() == {"content": MODEL_OUTPUT["message"]["content"]}
        assert len(calls) == 3
        assert client.post("/api/chat", json=CHAT).json() == response.json()
        assert len(calls) == 3  # UUID retry still uses the saved reply.
    store = ConversationStore(settings.resolved_job_storage_path)
    assert store.get_conversation(CHAT["conversationId"])["messages"][-1]["content"] == MODEL_OUTPUT["message"]["content"]


@pytest.mark.parametrize("body, expected", [
    ({"id": "job-123", "status": "FAILED", "error": "sensitive worker details"}, 502),
    ({"id": "job-123", "status": "CANCELLED"}, 502),
    ({"id": "job-123", "status": "TIMED_OUT"}, 504),
    ({"id": "job-123", "status": "COMPLETED", "output": []}, 502),
    ({"id": "job-123", "status": "COMPLETED", "output": {"error": "sensitive worker details"}}, 502),
    ({"id": "job-123", "status": "COMPLETED", "output": {"message": None}}, 502),
    ({"id": "job-123", "status": "COMPLETED", "output": {"message": {"content": ""}}}, 502),
    ({"id": "job-123", "status": "UNKNOWN"}, 502),
    ({"id": "../../other", "status": "IN_QUEUE"}, 502),
    ([], 502),
])
def test_invalid_and_failed_jobs_do_not_leak_details(settings, body, expected):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=body)

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        response = client.post("/api/chat", json=CHAT)
        assert response.status_code == expected
        assert "sensitive" not in response.text and "test-secret" not in response.text
        assert not client.app.state.agent_lock.locked()
    assert calls.count("/v2/endpoint-123/run") == 1


@pytest.mark.parametrize("status, expected", [(401, 503), (403, 503), (404, 503), (429, 503), (503, 503), (500, 502)])
def test_runpod_http_errors_are_sanitized_without_submission_retry(settings, status, expected):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "sensitive account information"})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        response = client.post("/api/chat", json=CHAT)
        assert response.status_code == expected
        assert "Ollama" not in response.text and "sensitive" not in response.text
    assert len(calls) == 1


def test_deadline_cancels_submitted_job_and_releases_lock(settings):
    settings.runpod_timeout_seconds = 0.025
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"id": "job-123", "status": "IN_QUEUE"})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        assert client.post("/api/chat", json=CHAT).status_code == 504
        assert not client.app.state.agent_lock.locked()
    assert calls[-1] == "/v2/endpoint-123/cancel/job-123"
    assert calls.count("/v2/endpoint-123/run") == 1


def test_job_match_overall_deadline_also_cancels_active_job(settings):
    settings.job_match_timeout_seconds = 0.02
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"id": "job-123", "status": "IN_PROGRESS"})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        assert client.post("/api/job-match", json={"jobDescription": "Python API development experience is required."}).status_code == 504
        assert not client.app.state.agent_lock.locked()
    assert calls[-1] == "/v2/endpoint-123/cancel/job-123"


def test_cancellation_failure_does_not_hide_timeout(settings):
    settings.runpod_timeout_seconds = 0.02

    def respond(request):
        if "/cancel/" in request.url.path:
            return httpx.Response(500, json={"error": "failure"})
        return httpx.Response(200, json={"id": "job-123", "status": "IN_QUEUE"})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        assert client.post("/api/chat", json=CHAT).status_code == 504


def test_ambiguous_submission_is_not_retried(settings):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        raise httpx.ReadTimeout("Submission may already have been accepted", request=request)

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        assert client.post("/api/chat", json=CHAT).status_code == 504
    assert calls == ["/v2/endpoint-123/run"]


def test_malformed_submission_json_does_not_resubmit_analysis(settings):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, text="not JSON")

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        assert client.post("/api/job-match", json={"jobDescription": "Python API development experience is required."}).status_code == 502
    assert calls == ["/v2/endpoint-123/run"]


def test_network_failure_during_poll_cancels_known_job(settings):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        if "/status/" in request.url.path:
            raise httpx.ConnectError("Unavailable", request=request)
        return httpx.Response(200, json={"id": "job-123", "status": "IN_QUEUE"})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        response = client.post("/api/chat", json=CHAT)
        assert response.status_code == 503 and "Runpod" in response.text
    assert calls[-1] == "/v2/endpoint-123/cancel/job-123"


def test_caller_task_cancellation_cancels_remote_job(settings):
    async def run():
        submitted = asyncio.Event()
        calls = []

        async def respond(request):
            calls.append(request.url.path)
            if "/status/" in request.url.path:
                submitted.set()
                await asyncio.sleep(10)
            return httpx.Response(200, json={"id": "job-123", "status": "IN_PROGRESS"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            task = asyncio.create_task(inference.generate(client, settings, messages=[], options={}, timeout=300))
            await asyncio.wait_for(submitted.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert calls[-1] == "/v2/endpoint-123/cancel/job-123"
    asyncio.run(run())


@pytest.mark.parametrize("changes", [
    {}, {"runpod_endpoint_id": "endpoint-123"}, {"runpod_api_key": "secret"},
    {"runpod_endpoint_id": "../unsafe", "runpod_api_key": "secret"},
    {"runpod_endpoint_id": "endpoint-123", "runpod_api_key": "  "},
])
def test_runpod_requires_valid_backend_configuration(changes):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, inference_provider="runpod", **changes)


def test_local_provider_does_not_require_runpod_credentials():
    settings = Settings(_env_file=None)
    assert settings.inference_provider == "ollama"


def test_key_is_redacted_in_settings_representation(settings):
    assert "test-secret" not in repr(settings)


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "deploy" / "runpod"))
    return importlib.import_module("worker")


def test_job_match_runs_both_schemas_through_real_worker_contract(settings, worker):
    extracted = {"jobTitle": None, "hasMoreRequirements": False, "requirements": [{
        "requirement": "Python API development", "importance": "required",
        "jobExcerpt": "Python API development experience is required.",
    }]}
    compared = {"assessments": [{
        "requirementId": "req-1", "status": "supported",
        "candidateEvidence": [{"sourceId": "source-1", "quote": "Developed Python APIs with FastAPI."}],
        "explanation": "The CV documents Python API development.", "followUpQuestion": None,
    }]}
    payloads = []

    def ollama(request):
        payloads.append(json.loads(request.content))
        assert isinstance(payloads[-1]["format"], dict)
        assert "num_gpu" not in payloads[-1]["options"]
        content = extracted if len(payloads) == 1 else compared
        return httpx.Response(200, json={"message": {"content": json.dumps(content)}, "done_reason": "stop"})

    with httpx.Client(transport=httpx.MockTransport(ollama)) as ollama_client:
        def runpod(request):
            assert request.url.path.endswith("/run")
            output = worker.handle_job(json.loads(request.content), client=ollama_client, model=settings.ollama_model)
            return httpx.Response(200, json={"id": "job-123", "status": "COMPLETED", "output": output})

        with TestClient(create_app(settings, httpx.MockTransport(runpod))) as client:
            response = client.post("/api/job-match", json={"jobDescription": "Python API development experience is required."})
            assert response.status_code == 200
            assert response.json()["requirements"][0]["status"] == "supported"
    assert len(payloads) == 2
    assert payloads[1]["options"]["num_ctx"] == settings.job_match_context_tokens
