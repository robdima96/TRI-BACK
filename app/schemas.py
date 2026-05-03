from pydantic import BaseModel, Field

# Pydantic BaseModel classes that describe the expected data shape of API requests and responses

class Evidence(BaseModel):
    source: str
    snippet: str
    score: float = Field(ge=0.0, le=1.0)


class EncoderEntity(BaseModel):
    text: str
    label: str


class ChecklistItem(BaseModel):
    """One structured finding from the encoder / extraction stack (orchestrator history)."""

    text: str
    kind: str
    # pattern | ner | safety_phrase
    source: str
    # optional: NER label, risk id, or pattern label (duration, comorbidity, severity, symptom_quality, provocative, palliative)
    label: str = ""


class ClinicalChecklist(BaseModel):
    items: list[ChecklistItem] = Field(default_factory=list)


class EncoderOutput(BaseModel):
    """Encoder / extraction output; ``pooled_embedding`` is for RAG when populated."""

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
