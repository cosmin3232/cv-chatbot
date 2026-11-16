"""Download only the selected model at image build time, never on a cold start."""

import os
import subprocess

from runtime import ollama_server

if __name__ == "__main__":
    model = os.environ["OLLAMA_MODEL"]
    with ollama_server():
        subprocess.run(["ollama", "pull", model], check=True, timeout=3600)
        subprocess.run(["ollama", "show", model], check=True, timeout=30)
