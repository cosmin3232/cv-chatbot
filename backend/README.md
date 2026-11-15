# CV Chatbot backend

FastAPI provides `POST /api/chat` and `POST /api/job-match`, backed by a local Ollama model. MCP, a vector database, and an agent framework are not needed for this MVP. Replies and job comparisons use reviewed CV information. Successfully extracted job uploads and accepted chat messages are saved in a private SQLite archive for the owner.

## Setup (PowerShell)

From `backend` with Python 3.11+ installed:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env
```

The development virtual environment has already been created for this checkout.

Install/start Ollama, then download the configured model:

```powershell
ollama pull qwen3:4b
```

If Ollama is not already running, run `ollama serve` in another terminal. An existing model can be selected by setting `OLLAMA_MODEL` in `.env`. This checkout currently has `llama3.1:8b` installed, but it has not been benchmarked for this workload. No new model was downloaded during setup.

## Import and review your documents

For fictional test data, run `.venv/Scripts/python.exe scripts/create_dummy_documents.py` from `backend`. It creates `data/dummy_cv.pdf`, `data/dummy_info.docx`, and the draft and active knowledge files. The generator refuses to overwrite existing documents or knowledge. Its data describes an invented candidate, Alex Marin. A local `data/test-questions.md` provides sample questions and expected facts. Replace the active knowledge when using your own CV.

Put your PDF CV and Word `.docx` file in `backend/data/`. Everything in that folder except `.gitkeep` is excluded from Git.

From `backend`:

```powershell
.venv/Scripts/python.exe -m app.ingest data/cv.pdf data/info.docx
```

This creates `data/knowledge.draft.md` and refuses to overwrite an existing draft. Review the text locally, fix PDF reading order, check dates and table content, and remove details recruiters should not receive. Then create the active knowledge file:

```powershell
Copy-Item data/knowledge.draft.md data/knowledge.md
```

Use a different `--output` path for subsequent imports or remove the old draft yourself. The API rereads the approved knowledge file for each request. Source labels such as `CV, page 1` are preserved for answer references. PDF image-only pages require OCR outside this importer. Word extraction covers body paragraphs and tables, not every possible embedded object, header, or footnote. Older `.doc` files must be converted to `.docx`.

Knowledge is limited to 12,000 characters; oversized documents are rejected rather than silently truncated. Shorten the reviewed file if needed. A missing or empty knowledge file returns a setup error without calling the model. Review generated answers too: prompt instructions and references reduce unsupported claims but do not guarantee factual answers.

## Run

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API documentation: http://localhost:8000/docs

`GET /health` reports API liveness, knowledge availability, and the configured model. It does not check whether Ollama or its model is ready.

From `frontend`, copy `.env.example` to `.env.local` if a custom backend URL is needed, then run `npm run dev`. The default URL is `http://localhost:8000`; the default allowed frontend origin is `http://localhost:3000`. Restart Next.js after changing `NEXT_PUBLIC_API_URL` (rebuild for production).

## API contract

```json
{
  "conversationId": "30c0e97b-fbf7-4d42-b1ca-03265d5ed870",
  "messageId": "e70cbeae-204c-4cbe-8fda-5d96263dff78",
  "prompt": "What technical experience does the candidate have?",
  "history": [{ "role": "user", "content": "Tell me about the candidate." }]
}
```

The prompt excludes previous messages. History may contain only `user` and `assistant` roles; client-supplied system messages are rejected. The response is `{ "content": "..." }`. The frontend validates this response at runtime.

`conversationId` must be a UUID and stays the same across every message in one conversation. Use a different UUID for each new conversation/session. `messageId` is an optional UUID identifying one prompt; the frontend supplies it, and the backend generates one when omitted. Retrying a completed message with the same IDs and prompt returns its saved reply without duplicating records or invoking the model again. Reusing a message ID for different text/conversation or resending a pending message returns 409. Failed messages can be retried with the same message ID.

## Saved conversations

The existing private SQLite database (`JOB_STORAGE_PATH`, default `backend/storage/job_descriptions.sqlite3`) now also contains `conversations` and `conversation_messages`. Existing job uploads are preserved. Each conversation has a UUID, title, and UTC timestamps. Each message has its own UUID, a conversation foreign key, role, content, timestamp, and status. An assistant message's `reply_to` references its user prompt. Messages are listed in insertion order; deleting a conversation through the owner command cascades to all its messages.

A UUID is generated in the browser on every chat page mount (including refresh), and each **New conversation** click always generates another UUID, even if the previous conversation is empty. Switching sidebar entries retains their IDs. Empty conversations are registered in SQLite only when their first prompt is accepted. A prompt is archived as `pending` before inference; the reply and `completed` status are saved together before returning success. Model failures preserve the prompt as `failed`. Abrupt server termination can leave a `pending` record; a new message ID or a new conversation can still be used afterward. Requests rejected during input validation, rate limiting, busy checks, or missing-CV checks are not archived.

Conversation history still comes from the bounded `history` field for model context. Only actual prompts and model replies are archived; resubmitted history is not inserted as new messages. Browser history and drafts are in memory and are not restored after a refresh. Removing a chat from the browser sidebar does not remove the owner's archive. A cancelled browser request may still complete on the server and be archived. No public conversation listing, retrieval, or delete endpoints are exposed, and IDs do not act as authenticated recruiter accounts.

Owner commands, run locally from `backend`:

```powershell
.venv/Scripts/python.exe -m app.saved_conversations list
.venv/Scripts/python.exe -m app.saved_conversations show CONVERSATION_UUID
.venv/Scripts/python.exe -m app.saved_conversations delete CONVERSATION_UUID
```

`list` also accepts `--limit` and `--offset`. Records remain until the owner deletes them. Database files and sidecars remain excluded from Git. Keep the database directory private on the host. The archive stores chat conversations only; the job-fit report flow remains separate.

Requests allow at most 2,000 prompt characters, 12 history messages, and 4,000 total history characters. The frontend retains only a contiguous recent history within those limits. The model uses an 8,192-token context and a 400-token output limit. Character limits are conservative estimates, not exact token counts; test with the actual documents and languages before deployment.

One agent request runs at a time per API process. Chat and job analysis share the generation lock and the default per-IP limit of 20 requests per minute (429). Busy requests return 503. Model timeouts return 504, Ollama connectivity errors 503, and invalid upstream responses 502. Deleting a conversation cancels the browser request; an already running server generation may finish until the server timeout.

## Job-match analysis (text input)

Start the backend as described above. Open `/docs` to try `POST /api/job-match`, or run this from `backend`:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/job-match `
  -Method Post -ContentType 'application/json' `
  -Body (Get-Content -Raw examples/job-match.json) -TimeoutSec 260 |
  ConvertTo-Json -Depth 12
```

The request is `{ "jobDescription": "..." }`. The server loads the reviewed CV itself; clients cannot override it. Open `http://localhost:3000/job-match` or choose **Analyze a job description** in the chat sidebar to paste text or upload a PDF/DOCX, review the extracted text, and request the report.

The report contains `jobTitle`, `summary`, `requirements`, `strengths`, `gaps`, `questions`, and `limitations`. Each requirement includes its stable report-local `id`, description, `importance`, original `jobExcerpt`, `status`, `candidateEvidence` (source ID, label and quote), `explanation`, and optional `followUpQuestion`. `strengths` and `gaps` contain requirement IDs for referencing the detailed entries. Unknown means the information is not established, not that the candidate lacks a skill. A gap requires explicit contradictory evidence; partial support and unknowns require a clarification question. The summary counts validated assessments and is constructed by the backend, not generated independently by the model.

Analysis has two stages: extract requirements from the description, then compare them against server-provided CV sections. Ollama receives JSON schemas, and Pydantic validates its output. The server checks quotations against their exact source section (ignoring whitespace), rejects invented source IDs and duplicated or omitted assessment IDs, and allows one correction attempt per stage. This makes two model calls normally, at most four with corrections. Exhausted validation failures return 502; incomplete token-limited output is never published as a report.

Input is limited to 30–8,000 characters. Up to 12 distinct requirements are supported; if the extraction model reports more, the API returns 422 and asks for a narrower description. Quote presence and schema validation cannot guarantee correct interpretations or complete extraction. In particular, a model could still mislabel a requirement or overlook one; use the manual evaluation cases in `examples/job-match-evaluation.md` before relying on results. No hiring decision or probability score is returned.

Job-analysis settings (also listed in `.env.example`):

| Setting | Default | Purpose |
| --- | --- | --- |
| `JOB_MATCH_TIMEOUT_SECONDS` | 240 | Total deadline across both stages and corrections |
| `JOB_MATCH_CONTEXT_TOKENS` | 16384 | Context window for structured comparisons |
| `JOB_MATCH_OUTPUT_TOKENS` | 4096 | Output limit per model call |

These budgets are independent of chat. Larger context windows need additional memory; measure latency with the installed model and actual documents. The deadline bounds the API request even when correction is needed. Character limits do not guarantee token fit for every language; reduce input or adjust the context after measurement. An already submitted Ollama generation may continue briefly after request cancellation.

If the installed Ollama GPU runner fails with a CUDA/toolchain error, set `OLLAMA_NUM_GPU=0` in `backend/.env` to request CPU-only inference for both chat and job analysis. Leaving it unset retains Ollama's automatic GPU selection. CPU inference can be slower; use a locally available model and measure latency. No driver changes or automatic model downloads are performed by the app.

`POST /api/job-description/extract` accepts one multipart `file` field and returns `{ "documentId": "...", "text": "...", "warnings": ["..."] }`. It uses neutral job-description labels, not CV labels. Uploads are limited to 5 MB, PDFs to 10 pages, and extracted text to 8,000 characters. Expanded DOCX archives are limited to 10 MB and 1,000 entries. Streamed request bodies are bounded before multipart parsing can spool a large file. Temporary extraction files and multipart files are cleaned up after the original bytes and extracted text are saved in SQLite; uploaded text never replaces `knowledge.md`. Scanned PDFs require OCR elsewhere or pasted text. Review the preview for extraction errors before submitting it for analysis.

## Private saved job descriptions

Successful PDF/DOCX uploads are automatically archived in `backend/storage/job_descriptions.sqlite3`. Set `JOB_STORAGE_PATH` in `backend/.env` to override this location; relative paths are resolved against `backend`, not the terminal's working directory. SQLite uses Python's standard library, so there is no separate database service or new dependency to install. The database is initialized on backend startup. Failure to initialize stops startup; failure to save an upload returns 503 instead of claiming success.

Each row contains a generated UUID, original basename (metadata only), media type, byte size, SHA-256 checksum, UTC upload timestamp, extraction status, extracted text, and the original file bytes as a SQLite BLOB. Keeping the file and text in one database transaction avoids separate filesystem/database consistency problems. Repeat uploads are saved as separate records. Rejected or unextractable uploads are not archived. Text pasted directly into analysis, recruiter edits after preview, and generated reports are not saved by this feature.

The archive has no public listing, retrieval, download, or delete routes, and no recruiter history UI. A returned document ID does not grant HTTP access. The owner reads it through filesystem access or the following local commands, run from `backend`:

```powershell
# List recent upload metadata (use --limit and --offset for pagination)
.venv/Scripts/python.exe -m app.saved_jobs list

# Show one upload's metadata and extracted text
.venv/Scripts/python.exe -m app.saved_jobs show DOCUMENT_ID

# Export the original upload or its extracted text to an explicit path
.venv/Scripts/python.exe -m app.saved_jobs export DOCUMENT_ID saved-job.docx
.venv/Scripts/python.exe -m app.saved_jobs export DOCUMENT_ID saved-job.txt --text

# Remove one record from the archive
.venv/Scripts/python.exe -m app.saved_jobs delete DOCUMENT_ID
```

Export refuses to overwrite an existing file. Uploads remain until the owner deletes them; no automatic expiry is configured. Deletion removes the archive record, not any prior exports or backups. `backend/storage/`, including SQLite WAL/SHM sidecars, is excluded from Git. Access is limited by the backend machine's filesystem permissions; do not serve this directory as static files. Back up SQLite using a SQLite-aware backup tool or stop the backend before copying the database and any remaining sidecar files.

Uploads share the per-IP rate limit and have a separate one-at-a-time extraction lock. Hostile document parsing still needs process-level resource isolation and proxy request limits before public deployment. The frontend supports cancellation, errors and retry; browser cancellation does not guarantee an already submitted local model generation stops immediately.

Live verification on this checkout succeeded for one FastAPI requirement using `llama3.1:8b`, `OLLAMA_NUM_GPU=0`, and an 8,192-token analysis context. It took about 120 seconds. Automatic GPU selection failed locally with a CUDA/PTX toolchain error. This single result does not establish accuracy or latency for longer descriptions; the configured default model remains `qwen3:4b` until explicitly changed or downloaded.

## Tests

```powershell
.venv/Scripts/python.exe -m pytest -q
```

Tests use synthetic documents and mocked Ollama responses; they do not assert model quality. Before public release, evaluate real recruiter questions against reviewed CV facts, missing information, and instruction-changing prompts.

## Hosting

This is a local development setup. Keep Ollama private and expose only the application through HTTPS when deploying. Rate limits and concurrency are process-local, so use one API worker for this configuration. Public deployment still needs a hosting decision, request-size limits at the proxy, correct trusted-proxy/IP settings, and an availability plan for the machine running Ollama. Source references are model-generated text, not independently verified citations. Streaming responses can be added after the basic model quality and latency are measured.
