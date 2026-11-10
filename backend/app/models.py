from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversationId: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=2000)
    history: list[Message] = Field(default_factory=list, max_length=12)

    @field_validator("prompt")
    @classmethod
    def nonempty_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt cannot be blank")
        return value

    @model_validator(mode="after")
    def bounded_history(self):
        if sum(len(message.content) for message in self.history) > 4000:
            raise ValueError("Conversation history is too long")
        return self


class ChatResponse(BaseModel):
    content: str = Field(min_length=1)
