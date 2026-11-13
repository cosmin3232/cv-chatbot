import asyncio

from fastapi import APIRouter, HTTPException, Request

from ..runtime import agent_session
from .models import JobMatchRequest, JobMatchResponse
from .service import TooManyRequirements, analyze_job_match

router = APIRouter(prefix="/api", tags=["Job match"])


@router.post("/job-match", response_model=JobMatchResponse)
async def job_match(payload: JobMatchRequest, request: Request):
    state = request.app.state
    async with agent_session(request) as knowledge:
        try:
            # Includes extraction, comparison, and any correction attempts.
            async with asyncio.timeout(state.settings.job_match_timeout_seconds):
                return await analyze_job_match(state.client, state.settings, payload.jobDescription, knowledge)
        except TooManyRequirements as exc:
            raise HTTPException(422, str(exc)) from exc
