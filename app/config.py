import os

from pathlib import Path



from pydantic import BaseModel



# load environment variables 

try:

    from dotenv import load_dotenv



    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

except ImportError:

    pass



# converts string env vars into Python booleans (settings-toggle)

def _env_bool(name: str, default: bool = False) -> bool:

    v = os.environ.get(name, "").strip().lower() # normalize

    if v in ("1", "true", "yes", "on"):

        return True

    if v in ("0", "false", "no", "off"):

        return False

    return default # return default if not a valid boolean



# converts string env vars into Python strings (settings-path)

def _env_str(name: str, default: str | None = None) -> str | None:

    v = os.environ.get(name, "").strip()

    return v if v else default



# converts string env vars into Python floats (settings-numeric)

def _env_float(name: str, default: float) -> float:

    v = os.environ.get(name, "").strip()

    if not v:

        return default

    return float(v)



# converts string env vars into Python integers (settings-numeric)

def _env_int(name: str, default: int) -> int:

    v = os.environ.get(name, "").strip()

    if not v:

        return default

    return int(v)



# Span NER (GliNER zero-shot) and RAG embeddings use different local model dirs.

DEFAULT_GLINER_MODEL_DIR = r"E:\DigiMSKbot\GliNER-BioMed"

DEFAULT_RAG_EMBEDDING_MODEL_DIR = r"E:\DigiMSKbot\Clinical_sBERT"

DEFAULT_GENERATOR_BACKEND = "local"

DEFAULT_LOCAL_MODEL_LABEL = "mistral-local"

DEFAULT_VERTEX_MODEL = "gemini-2.5-flash"

DEFAULT_VERTEX_LOCATION = "us-central1"


def _normalize_generator_backend(raw: str | None) -> str:
    value = (raw or DEFAULT_GENERATOR_BACKEND).strip().lower()
    aliases = {
        "mistral": "local",
        "hf": "local",
        "huggingface": "local",
        "gemini": "vertex",
        "google": "vertex",
        "gcp": "vertex",
    }
    normalized = aliases.get(value, value)
    if normalized not in ("local", "vertex"):
        raise ValueError(
            f"unsupported DIGIMSK_GENERATOR_BACKEND: {raw!r} "
            "(supported: local, vertex)"
        )
    return normalized


DEFAULT_DISPOSITION_MODE = "deterministic"
DEFAULT_GRAPH_INFERENCE = "heuristic"


def _normalize_disposition_mode(raw: str | None) -> str:
    """Disposition reasoning mode: deterministic traversal vs tool-using agent."""
    value = (raw or DEFAULT_DISPOSITION_MODE).strip().lower()
    aliases = {
        "det": "deterministic",
        "default": "deterministic",
        "graph": "deterministic",
        "agent": "agentic",
        "agentic_graph_rag": "agentic",
    }
    normalized = aliases.get(value, value)
    if normalized not in ("deterministic", "agentic"):
        raise ValueError(
            f"unsupported DIGIMSK_DISPOSITION_MODE: {raw!r} "
            "(supported: deterministic, agentic)"
        )
    return normalized


def _normalize_graph_inference(raw: str | None) -> str:
    """Graph condition inference backend (Bayesian is a future skeleton)."""
    value = (raw or DEFAULT_GRAPH_INFERENCE).strip().lower()
    if value not in ("heuristic", "bayesian"):
        raise ValueError(
            f"unsupported DIGIMSK_GRAPH_INFERENCE: {raw!r} "
            "(supported: heuristic, bayesian)"
        )
    return value





# Settings object with default values and type hints

class Settings(BaseModel):

    app_name: str = "DigiMSKbot"

    app_version: str = "0.1.0"

    environment: str = "dev"

    encoder_max_length: int = 256

    # RAG ingest + query embeddings (Clinical_sBERT via sentence-transformers by default).

    encoder_model_dir: str = DEFAULT_RAG_EMBEDDING_MODEL_DIR

    rag_embedding_backend: str = "sentence_transformers"

    rag_embedding_normalize: bool = True

    generator_model_dir: str = r"E:\DigiMSKbot\Mistral7Binstruct"

    # ``local`` (safetensors) or ``vertex`` (Gemini on Vertex AI).
    generator_backend: str = DEFAULT_GENERATOR_BACKEND

    generator_model: str = DEFAULT_VERTEX_MODEL

    vertex_project_id: str | None = None

    vertex_location: str = DEFAULT_VERTEX_LOCATION

    chroma_persist_path: str = "data/chroma"

    # Vector length for Chroma (probe Clinical_sBERT if unset; default 768 for common clinical SBERT).

    encoder_embedding_dim: int = 768

    rag_top_k: int = 3

    ner_load: bool = True

    gliner_model_dir: str = DEFAULT_GLINER_MODEL_DIR

    gliner_load: bool = True

    gliner_ner_threshold: float = 0.5

    # Path 1: Clinical_sBERT + Chroma semantic search + checklist→chunk lexical match → generator evidence.

    rag_load: bool = True

    # Path 2: Local graph traversal (checklist→factors; optional chunk seeds when RAG enabled).

    graphrag_load: bool = True

    graph_backend: str = "local"

    # Disposition reasoning: "deterministic" (traverse → single draft) or
    # "agentic" (tool-using agent over the same ground-truth graph/RAG).

    disposition_mode: str = DEFAULT_DISPOSITION_MODE

    # Max tool-calling steps for the agentic disposition path before a forced draft.

    agentic_max_steps: int = 6

    # Condition scorer used by deterministic graph traversal.
    graph_inference: str = DEFAULT_GRAPH_INFERENCE

    # Future Bayesian agent tool registration; off until a model is configured.
    agentic_bayesian_tool: bool = False

    # LLM cross-check for unmatched checklist → Factor mapping (pre-traversal).
    # When off, matching stays fully deterministic (regex / kind / fuzzy only).
    llm_factor_match: bool = False

    # Max deterministic intake questions per session before best-effort disposition.

    max_questions: int = 10

    session_store_dir: str = "data/sessions"

    # LangGraph SqliteSaver; thread_id maps to chat session_id.

    checkpoint_sqlite_path: str = "data/langgraph_checkpoints.sqlite"

    # Shared secret for study UI → bot chat calls. Empty = no auth (local default).
    bot_api_key: str | None = None

    # Sliding-window limits for POST /api/v1/chat (0 disables).
    chat_rate_limit: int = 60

    chat_rate_window_sec: int = 60



# load settings from environment variables

_GENERATOR_BACKEND = _normalize_generator_backend(
    _env_str("DIGIMSK_GENERATOR_BACKEND", DEFAULT_GENERATOR_BACKEND)
)

_DEFAULT_GENERATOR_MODEL = {
    "vertex": DEFAULT_VERTEX_MODEL,
    "local": DEFAULT_LOCAL_MODEL_LABEL,
}.get(_GENERATOR_BACKEND, DEFAULT_VERTEX_MODEL)

settings = Settings(

    encoder_max_length=int(_env_float("DIGIMSK_ENCODER_MAX_LENGTH", 256)),

    encoder_model_dir=_env_str("DIGIMSK_ENCODER_DIR", DEFAULT_RAG_EMBEDDING_MODEL_DIR)

    or DEFAULT_RAG_EMBEDDING_MODEL_DIR,

    rag_embedding_backend=_env_str("DIGIMSK_RAG_EMBEDDING_BACKEND", "sentence_transformers")

    or "sentence_transformers",

    rag_embedding_normalize=_env_bool("DIGIMSK_RAG_EMBEDDING_NORMALIZE", True),

    generator_model_dir=_env_str(

        "DIGIMSK_GENERATOR_DIR", r"E:\DigiMSKbot\Mistral7Binstruct"

    )

    or r"E:\DigiMSKbot\Mistral7Binstruct",

    generator_backend=_GENERATOR_BACKEND,

    generator_model=_env_str("DIGIMSK_GENERATOR_MODEL") or _DEFAULT_GENERATOR_MODEL,

    vertex_project_id=_env_str("DIGIMSK_VERTEX_PROJECT_ID"),

    vertex_location=_env_str("DIGIMSK_VERTEX_LOCATION", DEFAULT_VERTEX_LOCATION)
    or DEFAULT_VERTEX_LOCATION,

    chroma_persist_path=_env_str("DIGIMSK_CHROMA_PATH", "data/chroma")

    or "data/chroma",

    encoder_embedding_dim=_env_int("DIGIMSK_ENCODER_DIM", 768),

    rag_top_k=_env_int("DIGIMSK_RAG_TOP_K", 10),

    ner_load=_env_bool("DIGIMSK_LOAD_NER", True),

    gliner_model_dir=_env_str("DIGIMSK_GLINER_MODEL_DIR", DEFAULT_GLINER_MODEL_DIR)

    or DEFAULT_GLINER_MODEL_DIR,

    gliner_load=_env_bool("DIGIMSK_LOAD_GLINER", True),

    gliner_ner_threshold=_env_float(

        "DIGIMSK_GLINER_NER_THRESHOLD",

        _env_float("DIGIMSK_NER_SCORE_THRESHOLD", 0.5),

    ),

    rag_load=_env_bool(
        "DIGIMSK_RAG",
        _env_bool("DIGIMSK_LOAD_RAG", True),
    ),

    graphrag_load=_env_bool(
        "DIGIMSK_GRAPH_RAG",
        _env_bool("DIGIMSK_LOAD_GRAPHRAG", True),
    ),

    graph_backend=_env_str("DIGIMSK_GRAPH_BACKEND", "local") or "local",

    disposition_mode=_normalize_disposition_mode(
        _env_str("DIGIMSK_DISPOSITION_MODE", DEFAULT_DISPOSITION_MODE)
    ),

    agentic_max_steps=_env_int("DIGIMSK_AGENTIC_MAX_STEPS", 6),

    graph_inference=_normalize_graph_inference(
        _env_str("DIGIMSK_GRAPH_INFERENCE", DEFAULT_GRAPH_INFERENCE)
    ),

    agentic_bayesian_tool=_env_bool("DIGIMSK_AGENTIC_BAYESIAN_TOOL", False),

    llm_factor_match=_env_bool("DIGIMSK_LLM_FACTOR_MATCH", False),

    max_questions=_env_int("DIGIMSK_MAX_QUESTIONS", 10),

    session_store_dir=_env_str("DIGIMSK_SESSION_STORE_DIR", "data/sessions")

    or "data/sessions",

    checkpoint_sqlite_path=_env_str(

        "DIGIMSK_CHECKPOINT_SQLITE", "data/langgraph_checkpoints.sqlite"

    )

    or "data/langgraph_checkpoints.sqlite",

    bot_api_key=_env_str("DIGIMSK_BOT_API_KEY"),

    chat_rate_limit=_env_int("DIGIMSK_CHAT_RATE_LIMIT", 60),

    chat_rate_window_sec=_env_int("DIGIMSK_CHAT_RATE_WINDOW_SEC", 60),

)


def validate_retrieval_paths() -> None:
    """At least one evidence path (RAG or graph RAG) must be enabled."""
    if not settings.rag_load and not settings.graphrag_load:
        raise ValueError(
            "At least one of DIGIMSK_RAG or DIGIMSK_GRAPH_RAG must be enabled (set to 1)."
        )

