"""A real inference probe using the selected provider, without sending CV data."""

import asyncio
import sys

import httpx

from .config import Settings
from .inference import InferenceError, generate


async def check() -> None:
    settings = Settings()
    print(f"Testing {settings.inference_provider} with {settings.ollama_model}; a cold start may take several minutes.")
    async with httpx.AsyncClient() as client:
        result = await generate(
            client, settings, messages=[{"role": "user", "content": "Reply with exactly: worker ready"}],
            options={"temperature": 0, "num_ctx": 8192, "num_predict": 32},
            timeout=settings.chat_timeout_seconds,
        )
    content = result.get("message", {}).get("content", "")
    if not isinstance(content, str) or content.strip().lower().strip(".\"'!") != "worker ready":
        raise ValueError("The probe returned an unexpected answer; inspect worker/model configuration.")
    print("Inference probe passed: worker ready")


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except (InferenceError, httpx.HTTPError, TimeoutError, ValueError, AttributeError):
        print("Inference probe failed. Check backend provider settings, model availability, and worker logs.", file=sys.stderr)
        sys.exit(1)
