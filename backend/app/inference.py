"""Ollama's chat contract over local HTTP or a Runpod queue worker."""

import asyncio
import logging
import re

import httpx

from .config import Settings

logger = logging.getLogger(__name__)
RUNPOD_API_URL = "https://api.runpod.ai/v2"
POLL_INTERVAL_SECONDS = 1.0


class InferenceError(Exception):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _runpod_body(response: httpx.Response) -> dict:
    if response.is_error:
        if response.status_code in (401, 403, 404):
            raise InferenceError("The inference service is not configured correctly. Please contact the owner.", 503)
        if response.status_code in (429, 503):
            raise InferenceError("The inference service is busy. Please try again shortly.", 503)
        raise InferenceError("The inference service could not complete the request.")
    try:
        body = response.json()
    except ValueError:
        raise InferenceError("The inference service returned an invalid response.") from None
    if not isinstance(body, dict):
        raise InferenceError("The inference service returned an invalid response.")
    return body


async def _cancel_job(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> None:
    # Best effort only: a failed cancellation must never hide the original error.
    try:
        async with asyncio.timeout(5):
            response = await client.post(url, headers=headers, timeout=5)
            response.raise_for_status()
    except (httpx.HTTPError, TimeoutError):
        logger.warning("Could not cancel a submitted Runpod job; its execution policy still applies.")


async def _runpod_chat(client: httpx.AsyncClient, settings: Settings, payload: dict, timeout: float) -> dict:
    url = f"{RUNPOD_API_URL}/{settings.runpod_endpoint_id}"
    headers = {"Authorization": f"Bearer {settings.runpod_api_key.get_secret_value()}"}
    job_id = None
    terminal = False
    budget = min(timeout, settings.runpod_timeout_seconds)
    try:
        async with asyncio.timeout(budget):
            # Never retry submission: an ambiguous failure could otherwise bill two jobs.
            body = _runpod_body(await client.post(
                url + "/run", headers=headers, timeout=15,
                json={"input": payload, "policy": {
                    "executionTimeout": max(5000, int(budget * 1000)),
                    "ttl": max(10000, int((budget + 10) * 1000)),
                }},
            ))
            candidate_id = body.get("id")
            if not isinstance(candidate_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", candidate_id):
                raise InferenceError("The inference service returned an invalid job identifier.")
            job_id = candidate_id
            interval = POLL_INTERVAL_SECONDS
            while True:
                status = body.get("status")
                if status == "COMPLETED":
                    terminal = True
                    output = body.get("output")
                    if not isinstance(output, dict) or "error" in output:
                        raise InferenceError("The inference worker returned an invalid answer.")
                    return output
                if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                    terminal = True
                    if status == "TIMED_OUT":
                        raise TimeoutError("Runpod job timed out")
                    # Worker errors may contain document text or internal details.
                    raise InferenceError("The inference worker could not complete the request.")
                if status not in ("IN_QUEUE", "IN_PROGRESS"):
                    raise InferenceError("The inference service returned an unexpected job status.")
                await asyncio.sleep(interval)
                interval = min(interval * 1.5, 5)
                body = _runpod_body(await client.get(url + f"/status/{job_id}", headers=headers, timeout=15))
    finally:
        if job_id and not terminal:
            await asyncio.shield(_cancel_job(client, url + f"/cancel/{job_id}", headers))


async def generate(
    client: httpx.AsyncClient, settings: Settings, *, messages: list[dict],
    options: dict, timeout: float, format: dict | None = None,
) -> dict:
    payload = {"model": settings.ollama_model, "messages": messages,
               "stream": False, "think": False, "options": dict(options)}
    if format is not None:
        payload["format"] = format
    if settings.inference_provider == "runpod":
        return await _runpod_chat(client, settings, payload, timeout)
    if settings.ollama_num_gpu is not None:
        payload["options"]["num_gpu"] = settings.ollama_num_gpu
    response = await client.post(settings.ollama_url.rstrip("/") + "/api/chat", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
