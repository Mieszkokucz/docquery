from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="session")
def full_pdf_path() -> Path:
    p = DATA_DIR / "raw" / "raport_2024_pl.pdf"
    if not p.exists():
        pytest.skip(f"Full PDF nie istnieje: {p}")
    return p
