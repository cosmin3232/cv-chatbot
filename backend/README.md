# CV Chatbot backend

FastAPI provides `POST /api/chat` and calls a local Ollama model. MCP, a vector database, and an agent framework are not needed for this MVP. Replies use reviewed CV information plus bounded recent conversation history. No conversations are stored on the server.

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
  "conversationId": "unique-conversation-id",
  "prompt": "What technical experience does the candidate have?",
  "history": [{ "role": "user", "content": "Tell me about the candidate." }]
}
```

The prompt excludes previous messages. History may contain only `user` and `assistant` roles; client-supplied system messages are rejected. The response is `{ "content": "..." }`. The frontend validates this response at runtime.

Requests allow at most 2,000 prompt characters, 12 history messages, and 4,000 total history characters. The frontend retains only a contiguous recent history within those limits. The model uses an 8,192-token context and a 400-token output limit. Character limits are conservative estimates, not exact token counts; test with the actual documents and languages before deployment.

One generation runs at a time per API process. Busy requests return 503; per-IP limits default to 20 chat requests per minute (429). Model timeouts return 504, Ollama connectivity errors 503, and invalid upstream responses 502. Deleting a conversation cancels the browser request; an already running server generation may finish until the server timeout.

## Tests

```powershell
.venv/Scripts/python.exe -m pytest -q
```

Tests use synthetic documents and mocked Ollama responses; they do not assert model quality. Before public release, evaluate real recruiter questions against reviewed CV facts, missing information, and instruction-changing prompts.

## Hosting

This is a local development setup. Keep Ollama private and expose only the application through HTTPS when deploying. Rate limits and concurrency are process-local, so use one API worker for this configuration. Public deployment still needs a hosting decision, request-size limits at the proxy, correct trusted-proxy/IP settings, and an availability plan for the machine running Ollama. Source references are model-generated text, not independently verified citations. Streaming responses can be added after the basic model quality and latency are measured.
