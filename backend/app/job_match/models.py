from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_REQUIREMENTS = 12
Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JobMatchRequest(StrictModel):
    jobDescription: str = Field(min_length=30, max_length=8000)


class ExtractedRequirement(StrictModel):
    requirement: str = Field(min_length=1, max_length=200)
    importance: Literal["required", "preferred", "unspecified"]
    jobExcerpt: str = Field(min_length=8, max_length=400)


class ExtractedJob(StrictModel):
    jobTitle: str | None = Field(max_length=200)
    requirements: list[ExtractedRequirement] = Field(min_length=1, max_length=MAX_REQUIREMENTS)
    hasMoreRequirements: bool


class EvidenceQuote(StrictModel):
    sourceId: str = Field(min_length=1, max_length=40)
    quote: str = Field(min_length=12, max_length=600)


class Assessment(StrictModel):
    requirementId: str = Field(min_length=1, max_length=40)
    status: Literal["supported", "partial", "gap", "unknown"]
    candidateEvidence: list[EvidenceQuote] = Field(max_length=3)
    explanation: str = Field(min_length=10, max_length=600)
    followUpQuestion: str | None = Field(default=None, min_length=5, max_length=300)

    @model_validator(mode="after")
    def require_evidence(self):
        if self.status != "unknown" and not self.candidateEvidence:
            raise ValueError("Supported, partial and gap assessments require candidate evidence")
        if self.status == "unknown" and self.candidateEvidence:
            raise ValueError("Unknown assessments must not claim candidate evidence")
        if self.status in ("partial", "unknown") and not self.followUpQuestion:
            raise ValueError("Partial and unknown assessments require a follow-up question")
        return self


class Comparison(StrictModel):
    assessments: list[Assessment] = Field(min_length=1, max_length=MAX_REQUIREMENTS)


class CandidateEvidence(EvidenceQuote):
    source: Text


class RequirementAssessment(ExtractedRequirement):
    id: Text
    status: Literal["supported", "partial", "gap", "unknown"]
    candidateEvidence: list[CandidateEvidence]
    explanation: Text
    followUpQuestion: str | None


class JobMatchResponse(StrictModel):
    jobTitle: str | None
    summary: Text
    requirements: list[RequirementAssessment]
    strengths: list[str]
    gaps: list[str]
    questions: list[str]
    limitations: list[str]
