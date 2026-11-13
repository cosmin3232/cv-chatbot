from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.config import Settings
from app.main import create_app


def test_docx_preview_does_not_change_candidate_knowledge(tmp_path):
    profile = tmp_path / "knowledge.md"
    profile.write_text("Original candidate knowledge", encoding="utf-8")
    document = Document()
    document.add_paragraph("Full Stack Engineer. Required: Python development experience.")
    data = BytesIO()
    document.save(data)
    with TestClient(create_app(Settings(_env_file=None, knowledge_path=profile))) as client:
        response = client.post("/api/job-description/extract", files={"file": ("job.docx", data.getvalue())})
        assert response.status_code == 200
        assert "Python development" in response.json()["text"]
        assert "Job description" in response.json()["text"]
        assert "CV, page" not in response.json()["text"]
        assert response.json()["warnings"]
    assert profile.read_text(encoding="utf-8") == "Original candidate knowledge"


def test_rejected_uploads():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.post("/api/job-description/extract", files={"file": ("bad.exe", b"data")}).status_code == 415
        assert client.post("/api/job-description/extract", files={"file": ("empty.pdf", b"")}).status_code == 422
        assert client.post("/api/job-description/extract", files={"file": ("bad.pdf", b"not a PDF")}).status_code == 422
        assert client.post("/api/job-description/extract", files={"file": ("large.pdf", b"a" * (5 * 1024 * 1024 + 1))}).status_code == 413


def test_body_limit_includes_chunked_requests():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        def content():
            for _ in range(7):
                yield b"x" * 1024 * 1024
        response = client.post("/api/job-description/extract", content=content(), headers={"content-type": "multipart/form-data; boundary=test"})
        assert response.status_code == 413


def test_scanned_or_too_many_pdf_pages():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        for pages in (1, 11):
            writer = PdfWriter()
            for _ in range(pages):
                writer.add_blank_page(width=600, height=800)
            data = BytesIO()
            writer.write(data)
            response = client.post("/api/job-description/extract", files={"file": ("scan.pdf", data.getvalue())})
            assert response.status_code == 422


def test_expanded_docx_limit():
    data = BytesIO()
    with ZipFile(data, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("oversized.xml", "x" * (11 * 1024 * 1024))
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post("/api/job-description/extract", files={"file": ("huge.docx", data.getvalue())})
        assert response.status_code == 422


def test_extracted_text_limit():
    document = Document()
    document.add_paragraph("a" * 8001)
    data = BytesIO()
    document.save(data)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post("/api/job-description/extract", files={"file": ("long.docx", data.getvalue())})
        assert response.status_code == 422
