"""Centralna konfiguracja backendu — ścieżki, modele, parametry RAG."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"

PDF_PATH = DATA_DIR / "raw" / "raport_2024_pl.pdf"

VISION_CACHE_DIR = DATA_DIR / "extraction"
VISION_MODEL = "claude-haiku-4-5-20251001"

CHAT_MODEL = "claude-sonnet-4-20250514"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

CHUNK_SIZE = 999999
CHUNK_OVERLAP = 50
TOP_K = 5
