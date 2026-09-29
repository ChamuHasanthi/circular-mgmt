"""Environment-driven configuration (dev / prod).

All secrets and the database URL come from the environment (.env), so the same
code runs on SQLite during development and MySQL 8.0 for the thesis deployment.
"""
import os
from datetime import timedelta

from dotenv import load_dotenv

# Load backend/.env BEFORE the Config class body reads os.getenv(), otherwise
# values default before the file is parsed.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BACKEND_ROOT, ".env"))


class Config:
    # ---- Flask core ----
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    REPORT_BANK_NAME = os.getenv("REPORT_BANK_NAME", "Bank Compliance Office")

    # ---- Database ----
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///circular_management.sqlite3"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---- JWT (FR-01 auth, FR-03 30-min session) ----
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))
    )

    # ---- File upload (FR-06, FR-09) ----
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024

    # ---- AI models (NFR-08 local inference) ----
    SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_sm")
    BERT_MODEL = os.getenv("BERT_MODEL", "bert-base-uncased")
    BART_MODEL = os.getenv("BART_MODEL", "facebook/bart-large-cnn")
    BART_FALLBACK_MODEL = os.getenv(
        "BART_FALLBACK_MODEL", "sshleifer/distilbart-cnn-12-6"
    )
    SBERT_MODEL = os.getenv("SBERT_MODEL", "all-MiniLM-L6-v2")
    MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "model_cache")

    # ---- Local LLM summarizer via Ollama (offline, NFR-08) ----
    # When enabled and Ollama is reachable, summaries use a local instruction
    # LLM (far more fluent than BART); otherwise the pipeline falls back to BART.
    USE_LLM_SUMMARY = os.getenv("USE_LLM_SUMMARY", "true").lower() == "true"
    # Generate grounded RAG chatbot answers with the local LLM (vs extractive).
    USE_LLM_CHAT = os.getenv("USE_LLM_CHAT", "true").lower() == "true"
    # Minimum retrieval relevance (SBERT cosine sim of the best chunk). In global
    # search, if no chunk clears this, the bot replies "not found" without calling
    # the LLM — rejecting off-topic questions. 0 disables the gate.
    RAG_MIN_RELEVANCE = float(os.getenv("RAG_MIN_RELEVANCE", "0.25"))
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    # A smaller model for interactive chat (speed over depth). Falls back to
    # OLLAMA_MODEL if unset — e.g. set to "llama3.2:1b" for faster replies.
    OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "900"))  # 15 min for slow CPUs
    # Keep the model loaded between summaries (avoids reload cost).
    OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    # Upper bound on context window — lower it on small-VRAM GPUs so more of the
    # model fits on the GPU (e.g. 6144 for a 2GB card).
    OLLAMA_MAX_CTX = int(os.getenv("OLLAMA_MAX_CTX", "16384"))
    # GPU layers to offload: "0" forces full CPU (avoids slow CPU/GPU split on
    # weak GPUs); unset = let Ollama decide automatically.
    OLLAMA_NUM_GPU = os.getenv("OLLAMA_NUM_GPU")
    # Same, but for chat: "0" = full CPU (often faster than a split on weak GPUs),
    # unset = auto-place. Lets you benchmark chat independently of summaries.
    OLLAMA_CHAT_NUM_GPU = os.getenv("OLLAMA_CHAT_NUM_GPU")

    # ---- CORS ----
    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
