import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .agent import ask_agent
from .config import Settings
from .knowledge import load_knowledge
from .models import ChatRequest, ChatResponse
from .runtime import agent_session
from .job_match.routes import router as job_match_router
from .job_match.uploads import UploadBodyLimit, router as upload_router


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.client = client
            app.state.agent_lock = asyncio.Lock()
            app.state.document_lock = asyncio.Lock()
            app.state.requests = {}
            yield

    app = FastAPI(title="CV Chatbot API", lifespan=lifespan)
    app.state.settings = config
    app.include_router(job_match_router)
    app.include_router(upload_router)
    app.add_middleware(UploadBodyLimit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin],
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    async def health():
        try:
            await asyncio.to_thread(load_knowledge, config.resolved_knowledge_path)
            knowledge_ready = True
        except ValueError:
            knowledge_ready = False
        # Liveness/configuration only; this does not claim Ollama is ready.
        return {"status": "ok", "knowledgeReady": knowledge_ready, "model": config.ollama_model}

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest, request: Request):
        async with agent_session(request) as knowledge:
            content = await ask_agent(app.state.client, config, payload, knowledge)
        return ChatResponse(content=content)

    return app


app = create_app()
