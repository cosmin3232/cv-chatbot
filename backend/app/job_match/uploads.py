import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..ingest import extract_document
from ..runtime import enforce_rate_limit

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 65536
UPLOAD_PATH = "/api/job-description/extract"
router = APIRouter(tags=["Job match"])


class UploadBodyLimit:
    """Bound streamed multipart bytes before the parser can spool a large upload."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != UPLOAD_PATH:
            return await self.app(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > MAX_REQUEST_BYTES:
                raise HTTPException(413, "Upload exceeds the 5 MB file limit.")
            return message

        await self.app(scope, limited_receive, send)


class ExtractedDescription(BaseModel):
    text: str
    warnings: list[str]


def extract_upload(data: bytes, suffix: str) -> str:
    with TemporaryDirectory(prefix="cv-chatbot-jd-") as directory:
        path = Path(directory) / ("job-description" + suffix)
        path.write_bytes(data)
        if suffix == ".docx":
            with ZipFile(path) as archive:
                files = archive.infolist()
                if len(files) > 1000 or sum(item.file_size for item in files) > 10 * 1024 * 1024:
                    raise ValueError("Expanded Word document is too large.")
        return extract_document(path, pdf_label="Job description", docx_label="Job description", max_pages=10, max_characters=8000)


@router.post(UPLOAD_PATH, response_model=ExtractedDescription, openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}},
    }}}},
})
async def extract_description(request: Request):
    enforce_rate_limit(request)
    if request.app.state.document_lock.locked():
        raise HTTPException(503, "Another document is being processed. Please try again shortly.")
    async with request.app.state.document_lock:
        try:
            async with request.form(max_files=1, max_fields=0) as form:
                file = form.get("file")
                # Starlette creates the underlying UploadFile instance.
                if file is None or not hasattr(file, "filename"):
                    raise HTTPException(422, "Provide one PDF or DOCX in the file field.")
                suffix = Path(file.filename or "").suffix.lower()
                if suffix not in (".pdf", ".docx"):
                    raise HTTPException(415, "Only PDF and DOCX files are supported.")
                data = await file.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(413, "Upload exceeds 5 MB.")
                if not data:
                    raise HTTPException(422, "The uploaded file is empty.")
                try:
                    text = await asyncio.to_thread(extract_upload, data, suffix)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
                except Exception as exc:
                    raise HTTPException(422, "Could not extract this document. Try a text-based PDF, DOCX, or paste the description.") from exc
        except HTTPException:
            raise
        return ExtractedDescription(text=text, warnings=["Review the extracted text, reading order, and tables before analysis. Image-only PDFs require OCR."])
