import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .agent import ask_agent
from .config import Settings
from .knowledge import load_knowledge
from .models import ChatRequest, ChatResponse
from .runtime import agent_session
from .job_match.routes import router as job_match_router
from .job_match.uploads import UploadBodyLimit, router as upload_router
from .job_store import JobStore
from .conversation_store import ConversationStore, MessageConflict

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.job_store = JobStore(config.resolved_job_storage_path)
        await asyncio.to_thread(app.state.job_store.initialize)
        app.state.conversation_store = ConversationStore(config.resolved_job_storage_path)
        await asyncio.to_thread(app.state.conversation_store.initialize)
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
            store = app.state.conversation_store
            conversation_id, message_id = str(payload.conversationId), str(payload.messageId)
            try:
                cached = await asyncio.to_thread(store.begin_message, conversation_id, message_id, payload.prompt)
            except MessageConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except sqlite3.Error as exc:
                logger.exception("Could not save chat prompt")
                raise HTTPException(503, "The conversation could not be saved. Please try again.") from exc
            if cached is not None:
                return ChatResponse(content=cached)
            try:
                content = await ask_agent(app.state.client, config, payload, knowledge)
                await asyncio.to_thread(store.complete_message, conversation_id, message_id, content)
            except (Exception, asyncio.CancelledError) as exc:
                try:
                    await asyncio.shield(asyncio.to_thread(store.fail_message, conversation_id, message_id))
                except sqlite3.Error:
                    logger.exception("Could not mark chat prompt as failed")
                if isinstance(exc, sqlite3.Error):
                    logger.exception("Could not save assistant reply")
                    raise HTTPException(503, "The reply could not be saved. Please try again.") from exc
                raise
        return ChatResponse(content=content)

    return app


app = create_app()
