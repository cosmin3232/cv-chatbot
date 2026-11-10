import asyncio
from collections import deque
from contextlib import asynccontextmanager
from time import monotonic

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .agent import ask_agent
from .config import Settings
from .knowledge import load_knowledge
from .models import ChatRequest, ChatResponse


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.client = client
            app.state.agent_lock = asyncio.Lock()
            app.state.requests = {}
            yield

    app = FastAPI(title="CV Chatbot API", lifespan=lifespan)
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
        now = monotonic()
        visitors = app.state.requests
        expired = [key for key, entries in visitors.items() if not entries or entries[-1] <= now - 60]
        for key in expired:
            del visitors[key]
        address = request.client.host if request.client else "unknown"
        if address not in visitors and len(visitors) >= 10000:
            raise HTTPException(429, "Too many visitors. Please try again later.")
        entries = visitors.setdefault(address, deque())
        while entries and entries[0] <= now - 60:
            entries.popleft()
        if len(entries) >= config.requests_per_minute:
            raise HTTPException(429, "Too many requests. Please try again in a minute.", headers={"Retry-After": "60"})
        entries.append(now)
        try:
            knowledge = await asyncio.to_thread(load_knowledge, config.resolved_knowledge_path)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc

        if app.state.agent_lock.locked():
            raise HTTPException(503, "The agent is busy. Please try again shortly.", headers={"Retry-After": "3"})
        async with app.state.agent_lock:
            try:
                content = await ask_agent(app.state.client, config, payload, knowledge)
            except httpx.TimeoutException as exc:
                raise HTTPException(504, "The agent took too long to respond. Please try again.") from exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise HTTPException(503, "The configured model is unavailable. Ask the owner to pull it in Ollama.") from exc
                raise HTTPException(502, "Ollama could not complete the request.") from exc
            except httpx.RequestError as exc:
                raise HTTPException(503, "Ollama is unavailable. Please try again later.") from exc
            except (ValueError, TypeError, AttributeError) as exc:
                raise HTTPException(502, "The agent returned an invalid answer.") from exc
        return ChatResponse(content=content)

    return app


app = create_app()
