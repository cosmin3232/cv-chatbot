"""Start a private Ollama process, with bounded readiness and reliable cleanup."""

import os
import subprocess
import time
from contextlib import contextmanager

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"


@contextmanager
def ollama_server():
    environment = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"}
    process = subprocess.Popen(["ollama", "serve"], env=environment)
    try:
        deadline = time.monotonic() + 60
        with httpx.Client(timeout=2, trust_env=False) as client:
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Ollama exited before becoming ready.")
                try:
                    if client.get(OLLAMA_URL + "/api/tags").is_success:
                        break
                except httpx.RequestError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Ollama did not become ready within 60 seconds.")
                time.sleep(0.25)
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
