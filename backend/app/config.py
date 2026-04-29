"""Centralna konfiguracja backendu — ścieżki, modele, parametry RAG."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"

PDF_PATH = DATA_DIR / "raw" / "raport_2024_pl.pdf"

# Ekstrakcja (Claude Vision) — pozostaje pod "vision", bo dosłownie używa Vision API.
VISION_CACHE_DIR = DATA_DIR / "extraction_v2"
VISION_MODEL = "claude-sonnet-4-6"

# Konwersacja i retrieval (v2 pipeline RAG).
CHAT_MODEL = "claude-sonnet-4-6"
V2_EMBEDDING_MODEL = "text-embedding-3-small"
V2_CHUNK_MAX_CHARS = 800
V2_CHUNK_OVERLAP_CHARS = 0
V2_TOP_K = 5
