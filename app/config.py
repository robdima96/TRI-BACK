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

# Settings object with default values and type hints
class Settings(BaseModel):
    app_name: str = "DigiMSKbot"
    app_version: str = "0.1.0"
    environment: str = "dev"
    encoder_max_length: int = 256
    encoder_model_dir: str = r"E:\DigiMSKbot\GliNER-BioMed"
    generator_model_dir: str = r"E:\DigiMSKbot\Mistral7Binstruct"
    chroma_persist_path: str = "data/chroma"
    chroma_collection_name: str = "digimsk_evidence"
    # Mean-pooled encoder vector length = backbone hidden_size. GliNER-BioMed uses microsoft/deberta-v3-small (hidden_size 768 per HF config.json)
    encoder_embedding_dim: int = 768 
    rag_top_k: int = 3
    ner_model_id: str = "GliNER-BioMed"
    ner_load: bool = True
    # When False, skip Chroma retrieval and query embeddings for RAG (generator runs without citations).
    rag_load: bool = True
    session_store_dir: str = "data/sessions"
    # LangGraph SqliteSaver; thread_id maps to chat session_id.
    checkpoint_sqlite_path: str = "data/langgraph_checkpoints.sqlite"

# load settings from environment variables
settings = Settings(
    encoder_max_length=int(_env_float("DIGIMSK_ENCODER_MAX_LENGTH", 256)),
    encoder_model_dir=_env_str("DIGIMSK_ENCODER_DIR", r"E:\DigiMSKbot\GliNER-BioMed")
    or r"E:\DigiMSKbot\GliNER-BioMed",
    generator_model_dir=_env_str(
        "DIGIMSK_GENERATOR_DIR", r"E:\DigiMSKbot\Mistral7Binstruct"
    )
    or r"E:\DigiMSKbot\Mistral7Binstruct",
    chroma_persist_path=_env_str("DIGIMSK_CHROMA_PATH", "data/chroma")
    or "data/chroma",
    chroma_collection_name=_env_str("DIGIMSK_CHROMA_COLLECTION", "digimsk_evidence")
    or "digimsk_evidence",
    encoder_embedding_dim=_env_int("DIGIMSK_ENCODER_DIM", 768),
    rag_top_k=_env_int("DIGIMSK_RAG_TOP_K", 5),
    ner_model_id=_env_str("DIGIMSK_NER_MODEL_ID", "dslim/bert-base-NER")
    or "dslim/bert-base-NER",
    ner_load=_env_bool("DIGIMSK_LOAD_NER", False),
    rag_load=_env_bool("DIGIMSK_LOAD_RAG", True),
    session_store_dir=_env_str("DIGIMSK_SESSION_STORE_DIR", "data/sessions")
    or "data/sessions",
    checkpoint_sqlite_path=_env_str(
        "DIGIMSK_CHECKPOINT_SQLITE", "data/langgraph_checkpoints.sqlite"
    )
    or "data/langgraph_checkpoints.sqlite",
)
