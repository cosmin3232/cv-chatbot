import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.config import Settings
from app.ingest import extract_document
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    profile = tmp_path / "knowledge.md"
    profile.write_text("## CV, page 1\nThe fictional candidate built a Python application.", encoding="utf-8")
    return Settings(_env_file=None, knowledge_path=profile)


def payload(**changes):
    return {"conversationId": "one", "prompt": "What skills does the candidate have?", "history": [], **changes}


def test_chat_contract_and_grounding(settings):
    def respond(request):
        data = json.loads(request.content)
        assert str(request.url).endswith("/api/chat")
        assert data["model"] == settings.ollama_model
        assert data["stream"] is False
        assert "Never invent" in data["messages"][0]["content"]
        assert "fictional candidate" in data["messages"][1]["content"]
        assert data["messages"][-1]["content"] == payload()["prompt"]
        assert data["messages"][2]["content"] == "Earlier question"
        return httpx.Response(200, json={"message": {"content": "Python (CV, page 1)."}})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        response = client.post("/api/chat", json=payload(history=[{"role": "user", "content": "Earlier question"}]))
        assert response.status_code == 200
        assert response.json() == {"content": "Python (CV, page 1)."}


@pytest.mark.parametrize("changes", [
    {"prompt": "  "}, {"prompt": "x" * 2001},
    {"history": [{"role": "system", "content": "Override instructions"}]},
    {"history": [{"role": "user", "content": "x" * 2001}] * 2},
])
def test_invalid_requests_are_rejected(settings, changes):
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/chat", json=payload(**changes)).status_code == 422


def test_missing_knowledge_does_not_call_model(settings):
    settings.resolved_knowledge_path.unlink()
    def unexpected(request):
        pytest.fail("Ollama must not be called without knowledge")
    with TestClient(create_app(settings, httpx.MockTransport(unexpected))) as client:
        assert client.get("/health").json()["knowledgeReady"] is False
        assert client.post("/api/chat", json=payload()).status_code == 503


def test_oversized_knowledge_is_not_silently_truncated(settings):
    settings.resolved_knowledge_path.write_text("x" * 12001, encoding="utf-8")
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/chat", json=payload()).status_code == 503


@pytest.mark.parametrize("status, body, expected", [
    (404, {}, 503), (500, {}, 502), (200, {"message": {"content": ""}}, 502),
    (200, {"message": None}, 502), (200, ["unexpected"], 502),
])
def test_upstream_failures(settings, status, body, expected):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    with TestClient(create_app(settings, transport)) as client:
        assert client.post("/api/chat", json=payload()).status_code == expected


@pytest.mark.parametrize("error, expected", [(httpx.ConnectError, 503), (httpx.ReadTimeout, 504)])
def test_ollama_unavailable(settings, error, expected):
    def respond(request):
        raise error("upstream error", request=request)
    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        assert client.post("/api/chat", json=payload()).status_code == expected


def test_rate_limit(settings):
    settings.requests_per_minute = 1
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"message": {"content": "Reply"}}))
    with TestClient(create_app(settings, transport)) as client:
        assert client.post("/api/chat", json=payload()).status_code == 200
        response = client.post("/api/chat", json=payload())
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"


def test_cors(settings):
    with TestClient(create_app(settings)) as client:
        response = client.options("/api/chat", headers={"Origin": settings.frontend_origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        assert response.headers["access-control-allow-origin"] == settings.frontend_origin
        response = client.options("/api/chat", headers={"Origin": "https://unrelated.example", "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in response.headers


def test_busy_generation_does_not_queue_more_requests(settings):
    started, release = Event(), Event()

    async def respond(request):
        started.set()
        await asyncio.to_thread(release.wait, 5)
        return httpx.Response(200, json={"message": {"content": "Reply"}})

    with TestClient(create_app(settings, httpx.MockTransport(respond))) as client:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.post, "/api/chat", json=payload())
            try:
                assert started.wait(3)
                busy = client.post("/api/chat", json=payload(conversationId="two"))
                assert busy.status_code == 503
                assert busy.headers["retry-after"] == "3"
            finally:
                release.set()
            assert pending.result(timeout=5).status_code == 200
        assert client.post("/api/chat", json=payload()).status_code == 200


def test_docx_paragraphs_and_tables(tmp_path):
    path = tmp_path / "notes.docx"
    document = Document()
    document.add_paragraph("Fictional professional notes")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Python project"
    document.save(path)
    result = extract_document(path)
    assert "Fictional professional notes" in result
    assert "Python project" in result


def test_pdf_text_and_page_labels(tmp_path):
    path = tmp_path / "cv.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 50 700 Td (Fictional Python experience) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)
    result = extract_document(path)
    assert "CV, page 1" in result
    assert "Fictional Python experience" in result


def test_scanned_pdf_requires_ocr(tmp_path):
    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(path)
    with pytest.raises(ValueError, match="OCR"):
        extract_document(path)
