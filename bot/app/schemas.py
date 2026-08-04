from pydantic import BaseModel, Field

# Pydantic BaseModel classes that describe the expected data shape of API requests and responses

class Evidence(BaseModel):
    source: str
    snippet: str
    score: float = Field(ge=0.0, le=1.0)
    chunk_id: str | None = None


class ChunkMatch(BaseModel):
    chunk_id: str
    source: str
    snippet: str
    score: float = Field(ge=0.0, le=1.0)
    sub_collection: str = "red_flags"


class EncoderEntity(BaseModel):
    text: str
    label: str


class ChecklistItem(BaseModel):
    """One structured finding from the encoder / extraction stack (orchestrator history)."""

    text: str
    kind: str
    # pattern | gliner | safety_phrase
    source: str
    # optional: NER label, risk id, or pattern label (demographic, duration, comorbidity, ...)
    label: str = ""


class ClinicalChecklist(BaseModel):
    items: list[ChecklistItem] = Field(default_factory=list)


class EncoderOutput(BaseModel):
    """Encoder output; ``pooled_embedding`` is the full-message vector for RAG when populated."""

    entities: list[EncoderEntity] = Field(default_factory=list)
    pooled_embedding: list[float] = Field(default_factory=list)
    checklist: ClinicalChecklist = Field(default_factory=ClinicalChecklist)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    citations: list[Evidence]
    escalated: bool
    safety_reason: str | None = None
    # UI: gathering information (one intake question) vs recommendation (disposition path).
    question_mode: bool = False
    questions_asked: int = 0
    coverage_ready: bool = False
    graph_traversal: dict | None = None
    matched_factors: list[str] = Field(default_factory=list)
    candidate_conditions: list[str] = Field(default_factory=list)
    traversed_chunk_ids: list[str] = Field(default_factory=list)
    factor_matching_audit: dict | None = None
    clinical_checklist: list[dict[str, str]] = Field(default_factory=list)
    extraction_history: list[dict] = Field(default_factory=list)
    turn_extraction: dict | None = None
