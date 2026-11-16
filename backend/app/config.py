from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore", hide_input_in_errors=True)

    inference_provider: Literal["ollama", "runpod"] = "ollama"
    runpod_endpoint_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    runpod_api_key: SecretStr | None = None
    # Includes queueing and cold start, rather than just model execution.
    runpod_timeout_seconds: float = Field(default=300, gt=0, le=300)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_num_gpu: int | None = Field(default=None, ge=0, le=256)
    ollama_timeout_seconds: float = Field(default=120, gt=0, le=300)
    frontend_origin: str = "http://localhost:3000"
    knowledge_path: Path = Path("data/knowledge.md")
    job_storage_path: Path = Path("storage/job_descriptions.sqlite3")
    requests_per_minute: int = Field(default=20, ge=1, le=1000)
    job_match_timeout_seconds: float = Field(default=240, gt=0, le=600)
    job_match_context_tokens: int = Field(default=16384, ge=8192, le=32768)
    job_match_output_tokens: int = Field(default=4096, ge=1024, le=8192)

    @model_validator(mode="after")
    def require_runpod_credentials(self):
        if self.inference_provider == "runpod" and (
            not self.runpod_endpoint_id or not self.runpod_api_key
            or not self.runpod_api_key.get_secret_value().strip()
        ):
            raise ValueError("Runpod requires RUNPOD_ENDPOINT_ID and RUNPOD_API_KEY in backend configuration.")
        return self

    @property
    def chat_timeout_seconds(self) -> float:
        return self.runpod_timeout_seconds if self.inference_provider == "runpod" else self.ollama_timeout_seconds

    @property
    def resolved_knowledge_path(self) -> Path:
        if self.knowledge_path.is_absolute():
            return self.knowledge_path
        return BACKEND_DIR / self.knowledge_path

    @property
    def resolved_job_storage_path(self) -> Path:
        if self.job_storage_path.is_absolute():
            return self.job_storage_path
        return BACKEND_DIR / self.job_storage_path
