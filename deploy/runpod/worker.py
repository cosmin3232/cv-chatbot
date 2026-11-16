"""One Runpod job -> one Ollama chat completion, including JSON-schema output."""

import os
import signal
import subprocess
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

OLLAMA_URL = "http://127.0.0.1:11434"


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=60000)


class GenerationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature: float = Field(default=0.2, ge=0, le=2, allow_inf_nan=False)
    num_ctx: int = Field(default=8192, ge=8192, le=32768, strict=True)
    num_predict: int = Field(default=400, ge=1, le=8192, strict=True)


class InferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    model: str = Field(min_length=1, max_length=200)
    messages: list[Message] = Field(min_length=1, max_length=32)
    stream: Literal[False] = False
    think: Literal[False] = False
    options: GenerationOptions = Field(default_factory=GenerationOptions)
    format: dict | Literal["json"] | None = None

    @model_validator(mode="after")
    def bound_total_input(self):
        if sum(len(message.content) for message in self.messages) > 100000:
            raise ValueError("Too much message content")
        return self


def handle_job(job: dict, *, client: httpx.Client | None = None, model: str | None = None) -> dict:
    try:
        request = InferenceInput.model_validate(job["input"])
    except (ValidationError, KeyError, TypeError):
        raise ValueError("Invalid inference input. Check messages and generation limits.") from None
    configured_model = model or os.environ["OLLAMA_MODEL"]
    if request.model != configured_model:
        raise ValueError("The requested model does not match the worker's baked model.")
    payload = request.model_dump(exclude_none=True)
    # Keep the model loaded between jobs; Runpod controls worker scale-down.
    payload["keep_alive"] = "10m"
    try:
        if client is None:
            with httpx.Client(timeout=300, trust_env=False) as owned_client:
                return _complete(owned_client, payload)
        return _complete(client, payload)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        # Avoid exposing request/document content through Runpod error responses.
        raise RuntimeError("Ollama could not produce a valid completion. Check worker logs and model configuration.") from None


def _complete(client: httpx.Client, payload: dict) -> dict:
    response = client.post(OLLAMA_URL + "/api/chat", json=payload)
    response.raise_for_status()
    body = response.json()
    message = body.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str) or not message["content"].strip():
        raise ValueError("Missing completion")
    return {"message": {"role": "assistant", "content": message["content"]},
            "done": body.get("done", True), "done_reason": body.get("done_reason", "stop")}


def main():
    import runpod
    from runtime import ollama_server

    # Turn SIGTERM into normal stack unwinding so the Ollama child is reaped.
    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    with ollama_server():
        # Fail startup on a missing model; do not download during job execution.
        subprocess.run(["ollama", "show", os.environ["OLLAMA_MODEL"]], check=True, timeout=30)
        runpod.serverless.start({"handler": handle_job})


if __name__ == "__main__":
    main()
