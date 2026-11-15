from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.conversation_store import ConversationStore, MessageConflict
from app.job_store import JobStore
from app.main import create_app
from app.saved_conversations import main as owner_command


@pytest.fixture
def config(tmp_path):
    profile = tmp_path / "knowledge.md"
    profile.write_text("## CV, page 1\nA fictional candidate knows Python.", encoding="utf-8")
    return Settings(_env_file=None, knowledge_path=profile)


def request_body(conversation_id, **changes):
    return {"conversationId": conversation_id, "messageId": str(uuid4()), "prompt": "Tell me about Python experience.", **changes}


def test_conversation_contains_multiple_messages_and_survives_restart(config):
    conversation_id, other_id = str(uuid4()), str(uuid4())
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"message": {"content": f"Reply {calls}"}})

    with TestClient(create_app(config, httpx.MockTransport(respond))) as client:
        assert client.post("/api/chat", json=request_body(conversation_id)).status_code == 200
        assert client.post("/api/chat", json=request_body(conversation_id, prompt="What projects?", history=[{"role": "assistant", "content": "Not a new message"}])).status_code == 200
        assert client.post("/api/chat", json=request_body(other_id)).status_code == 200

    with TestClient(create_app(config)) as client:
        store = client.app.state.conversation_store
        conversation = store.get_conversation(conversation_id)
        assert conversation["id"] == conversation_id
        assert [message["role"] for message in conversation["messages"]] == ["user", "assistant", "user", "assistant"]
        assert [message["content"] for message in conversation["messages"]] == ["Tell me about Python experience.", "Reply 1", "What projects?", "Reply 2"]
        assert all(message["status"] == "completed" for message in conversation["messages"])
        for message in conversation["messages"]:
            UUID(message["id"])
        assert conversation["messages"][1]["reply_to"] == conversation["messages"][0]["id"]
        assert len(store.get_conversation(other_id)["messages"]) == 2
        assert len(store.list_conversations()) == 2
        for path in ("/api/conversations", f"/api/conversations/{conversation_id}"):
            assert client.get(path).status_code == 404


def test_user_prompt_is_saved_before_inference(config):
    conversation_id = str(uuid4())
    store = ConversationStore(config.resolved_job_storage_path)

    def respond(request):
        message = store.get_conversation(conversation_id)["messages"][0]
        assert message["role"] == "user" and message["status"] == "pending"
        return httpx.Response(200, json={"message": {"content": "Answer"}})

    with TestClient(create_app(config, httpx.MockTransport(respond))) as client:
        assert client.post("/api/chat", json=request_body(conversation_id)).status_code == 200


def test_message_id_makes_successful_retries_idempotent(config):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"message": {"content": "Saved reply"}})

    body = request_body(str(uuid4()))
    with TestClient(create_app(config, httpx.MockTransport(respond))) as client:
        for _ in range(2):
            assert client.post("/api/chat", json=body).json() == {"content": "Saved reply"}
        assert len(calls) == 1
        assert len(client.app.state.conversation_store.get_conversation(body["conversationId"])["messages"]) == 2
        assert client.post("/api/chat", json={**body, "prompt": "A different prompt"}).status_code == 409
        assert client.post("/api/chat", json={**body, "conversationId": str(uuid4())}).status_code == 409


def test_failed_attempts_are_preserved_and_can_be_retried(config):
    responses = iter([httpx.Response(500, json={"error": "failure"}), httpx.Response(200, json={"message": {"content": "Recovered"}})])
    body = request_body(str(uuid4()))
    with TestClient(create_app(config, httpx.MockTransport(lambda request: next(responses)))) as client:
        assert client.post("/api/chat", json=body).status_code == 502
        messages = client.app.state.conversation_store.get_conversation(body["conversationId"])["messages"]
        assert len(messages) == 1 and messages[0]["status"] == "failed"
        assert client.post("/api/chat", json=body).status_code == 200
        messages = client.app.state.conversation_store.get_conversation(body["conversationId"])["messages"]
        assert len(messages) == 2 and all(message["status"] == "completed" for message in messages)


@pytest.mark.parametrize("field", ["conversationId", "messageId"])
def test_invalid_uuid_is_rejected_before_inference(config, field):
    def unexpected(request):
        pytest.fail("Invalid IDs must not reach Ollama")
    with TestClient(create_app(config, httpx.MockTransport(unexpected))) as client:
        assert client.post("/api/chat", json=request_body(str(uuid4()), **{field: "initial"})).status_code == 422
        assert client.app.state.conversation_store.list_conversations() == []


@pytest.mark.parametrize("operation", ["begin_message", "complete_message"])
def test_archive_failures_return_error_instead_of_unsaved_success(config, monkeypatch, operation):
    body = request_body(str(uuid4()))
    with TestClient(create_app(config, httpx.MockTransport(lambda request: httpx.Response(200, json={"message": {"content": "Reply"}})))) as client:
        def fail(*args):
            raise sqlite3.OperationalError("private database path")
        monkeypatch.setattr(client.app.state.conversation_store, operation, fail)
        response = client.post("/api/chat", json=body)
        assert response.status_code == 503
        assert "private database path" not in response.text
        conversation = client.app.state.conversation_store.get_conversation(body["conversationId"])
        if operation == "begin_message":
            assert conversation is None
        else:
            assert [message["status"] for message in conversation["messages"]] == ["failed"]


def test_archive_upgrade_keeps_saved_job_uploads(config):
    jobs = JobStore(config.resolved_job_storage_path)
    jobs.initialize()
    document_id = jobs.save_upload("job.pdf", b"example", "Job description")
    with TestClient(create_app(config)) as client:
        assert client.app.state.job_store.get_upload(document_id)["extracted_text"] == "Job description"
        assert client.app.state.conversation_store.list_conversations() == []


def test_concurrent_message_retries_create_one_pending_row(config):
    store = ConversationStore(config.resolved_job_storage_path)
    store.initialize()
    conversation_id, message_id = str(uuid4()), str(uuid4())

    def begin(_):
        try:
            store.begin_message(conversation_id, message_id, "A prompt")
            return "created"
        except MessageConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(begin, range(4)))
    assert results.count("created") == 1
    assert len(store.get_conversation(conversation_id)["messages"]) == 1


def test_owner_commands_and_cascading_delete(config, capsys):
    store = ConversationStore(config.resolved_job_storage_path)
    store.initialize()
    conversation_id, message_id = str(uuid4()), str(uuid4())
    store.begin_message(conversation_id, message_id, "Candidate experience?")
    store.complete_message(conversation_id, message_id, "Python experience.")
    owner_command(["list"])
    assert json.loads(capsys.readouterr().out)[0]["message_count"] == 2
    owner_command(["show", conversation_id])
    assert len(json.loads(capsys.readouterr().out)["messages"]) == 2
    owner_command(["delete", conversation_id])
    capsys.readouterr()
    assert store.get_conversation(conversation_id) is None
    with sqlite3.connect(config.resolved_job_storage_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0] == 0
    with pytest.raises(SystemExit):
        owner_command(["show", conversation_id])
