from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
import sqlite3
from uuid import UUID

from docx import Document
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.job_store import JobStore
from app.main import create_app
from app.saved_jobs import main as archive_command


def docx_bytes():
    document = Document()
    document.add_paragraph("Backend Engineer. Python and SQL experience required.")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def test_upload_is_saved_and_survives_app_restart(tmp_path):
    config = Settings(_env_file=None)
    data = docx_bytes()
    with TestClient(create_app(config)) as client:
        response = client.post("/api/job-description/extract", files={"file": ("Backend Engineer.docx", data)})
        assert response.status_code == 200
        document_id = response.json()["documentId"]
        UUID(document_id)
        expected_text = response.json()["text"]
    with TestClient(create_app(config)) as client:
        stored = client.app.state.job_store.get_upload(document_id, include_file=True)
        assert stored["original_file"] == data
        assert stored["extracted_text"] == expected_text
        assert stored["original_filename"] == "Backend Engineer.docx"
        assert stored["byte_size"] == len(data)
        assert stored["sha256"] == sha256(data).hexdigest()
        assert stored["status"] == "extracted"
        assert stored["uploaded_at"].endswith("+00:00")
        assert "original_file" not in client.app.state.job_store.list_uploads()[0]
        assert "original_file" not in client.app.state.job_store.get_upload(document_id)
        # Neither IDs nor guessed paths expose the owner's archive over HTTP.
        for path in (f"/api/job-descriptions/{document_id}", "/api/job-descriptions", "/storage/job_descriptions.sqlite3"):
            assert client.get(path).status_code == 404


def test_invalid_upload_is_not_saved():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post("/api/job-description/extract", files={"file": ("broken.pdf", b"invalid")})
        assert response.status_code == 422
        assert client.app.state.job_store.list_uploads() == []


def test_database_write_failure_does_not_report_success(monkeypatch):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        def fail(*args):
            raise sqlite3.OperationalError("private database path /owner/private")
        monkeypatch.setattr(client.app.state.job_store, "save_upload", fail)
        response = client.post("/api/job-description/extract", files={"file": ("job.docx", docx_bytes())})
        assert response.status_code == 503
        assert "private database path" not in response.text
        assert client.app.state.job_store.list_uploads() == []


def test_parameterized_metadata_and_concurrent_uploads(tmp_path):
    store = JobStore(tmp_path / "archive.sqlite3")
    store.initialize()
    filename = "../../job'); DROP TABLE job_descriptions;--.pdf"
    document_id = store.save_upload(filename, b"sample", "Extracted job description")
    assert store.get_upload(document_id)["original_filename"].startswith("job'); DROP")
    assert store.get_upload("' OR 1=1 --") is None
    assert store.delete_upload("' OR 1=1 --") is False
    long_name = store.save_upload("a" * 300 + ".docx", b"test", "Some text")
    assert len(store.get_upload(long_name)["original_filename"]) == 255
    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(lambda index: store.save_upload(f"job{index}.pdf", b"data", "Job text"), range(8)))
    assert len(set(ids)) == 8
    assert len(store.list_uploads()) == 10
    assert store.delete_upload(document_id)
    assert store.get_upload(document_id) is None
    assert len(store.list_uploads(limit=2, offset=1)) == 2


def test_local_owner_commands(tmp_path, capsys):
    store = JobStore(Settings(_env_file=None).resolved_job_storage_path)
    store.initialize()
    document_id = store.save_upload("test.pdf", b"original bytes", "Extracted text")
    archive_command(["list"])
    assert json.loads(capsys.readouterr().out)[0]["id"] == document_id
    archive_command(["show", document_id])
    assert json.loads(capsys.readouterr().out)["extracted_text"] == "Extracted text"
    target = tmp_path / "export.pdf"
    archive_command(["export", document_id, str(target)])
    capsys.readouterr()
    assert target.read_bytes() == b"original bytes"
    with pytest.raises(SystemExit) as exc:
        archive_command(["export", document_id, str(target)])
    assert exc.value.code == 1
    assert target.read_bytes() == b"original bytes"
    text_target = tmp_path / "job.txt"
    archive_command(["export", document_id, str(text_target), "--text"])
    capsys.readouterr()
    assert text_target.read_text() == "Extracted text"
    archive_command(["delete", document_id])
    capsys.readouterr()
    assert store.get_upload(document_id) is None
    with pytest.raises(SystemExit) as exc:
        archive_command(["show", document_id])
    assert exc.value.code == 1
