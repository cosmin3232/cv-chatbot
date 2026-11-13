"""Shared knowledge, throttling and Ollama error handling for all agent routes."""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from time import monotonic

import httpx
from fastapi import HTTPException, Request

from .knowledge import load_knowledge


def enforce_rate_limit(request: Request):
    state = request.app.state
    config = state.settings
    now = monotonic()
    visitors = state.requests
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


@asynccontextmanager
async def agent_session(request: Request):
    state = request.app.state
    config = state.settings
    enforce_rate_limit(request)
    try:
        knowledge = await asyncio.to_thread(load_knowledge, config.resolved_knowledge_path)
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc

    if state.agent_lock.locked():
        raise HTTPException(503, "The agent is busy. Please try again shortly.", headers={"Retry-After": "3"})
    async with state.agent_lock:
        try:
            yield knowledge
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise HTTPException(504, "The agent took too long to respond. Please try again.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(503, "The configured model is unavailable. Ask the owner to pull it in Ollama.") from exc
            raise HTTPException(502, "Ollama could not complete the request.") from exc
        except httpx.RequestError as exc:
            raise HTTPException(503, "Ollama is unavailable. Please try again later.") from exc
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(502, "The agent returned an invalid or unverifiable answer. Please try again.") from exc
