from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = Field(default=120, gt=0, le=300)
    frontend_origin: str = "http://localhost:3000"
    knowledge_path: Path = Path("data/knowledge.md")
    requests_per_minute: int = Field(default=20, ge=1, le=1000)

    @property
    def resolved_knowledge_path(self) -> Path:
        if self.knowledge_path.is_absolute():
            return self.knowledge_path
        return BACKEND_DIR / self.knowledge_path
