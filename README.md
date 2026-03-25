# DocQuery — asystent RAG do raportu rocznego BGK

Aplikacja umozliwiajaca zadawanie pytan o raport roczny BGK w jezyku naturalnym. System odpowiada na podstawie tresci dokumentu, cytujac konkretne strony. Gdy informacji brak w raporcie — odmawia odpowiedzi zamiast halucynowac.

## Stack technologiczny

| Komponent | Technologia | Dlaczego |
|---|---|---|
| Backend API | FastAPI | Szybki, typowany, auto-dokumentacja (Swagger) |
| Frontend | Streamlit | Wbudowane komponenty chatowe, zero JS |
| Ekstrakcja PDF | PyMuPDF | Szybki, lekki, tekst per strona z metadanymi |
| Baza wektorowa | ChromaDB (in-memory) | Zero konfiguracji, wystarczy dla demo |
| Embeddingi | sentence-transformers (multilingual-e5-small) | Darmowy, lokalny, dziala z polskim tekstem |
| LLM | Claude (Anthropic API) |  mam zasilone $ |
| Konteneryzacja | Docker Compose | Jednokomendowy setup |

## Architektura

### Indeksowanie (startup backendu)

```
PDF --> PyMuPDF (tekst per strona) --> chunking --> embeddingi (e5-small) --> ChromaDB
```

### Obsluga zapytania

```
Pytanie uzytkownika
    |
    v
Retrieval: wyszukiwanie top-k fragmentow w ChromaDB
    |
    v
Budowanie prompta: kontekst (fragmenty) + historia konwersacji + pytanie
    |
    v
Claude API --> odpowiedz z cytatami [Strona N]
    |
    v
Filtrowanie zrodel do cytowanych stron --> odpowiedz + lista zrodel
```

Backend utrzymuje historie konwersacji per sesja (in-memory), co pozwala na pytania kontekstowe ("a co z tym?").

## Uruchomienie

### Wymagania

- Docker + Docker Compose
- Klucz API Anthropic

### Docker (zalecane)

```bash
git clone <repo-url>
cd docquery
cp .env.example .env
# Wpisz ANTHROPIC_API_KEY w pliku .env
docker-compose up --build
```

- Frontend: http://localhost:8501
- Backend API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs

### Lokalnie (bez Dockera)

```bash
pip install uv
uv sync
```

Terminal 1 (backend):
```bash
uv run uvicorn backend.app.main:app --reload
```

Terminal 2 (frontend):
```bash
uv run streamlit run frontend/app.py
```

## Zmienne srodowiskowe

| Zmienna | Wymagana | Opis |
|---|---|---|
| `ANTHROPIC_API_KEY` | Tak | Klucz API do Claude |

Plik `.env.example` zawiera wzor konfiguracji.

## Nota: dlaczego Docker build trwa dlugo

`sentence-transformers` (uzywany w `vector_store.py` do embeddingow) instaluje PyTorch z pelnym GPU stack (nvidia-cublas, nvidia-cudnn, triton, itp.). Stad duzy obraz Dockera (~2.5 GB samego PyTorch + CUDA) i dlugi build.


- **ALTERNATWA: OpenAI embeddings zamiast lokalnych**: usunac sentence-transformers, uzyc API OpenAI. Zero torch, lekki obraz, ale wymaga dodatkowego klucza (OPENAI_API_KEY)

## Mozliwe usprawnienia

- **Chunking po akapitach/zdaniach** — obecny dzieli po stalej liczbie znakow per strona, co moze rozcinac zdania. Lepiej: podzial po akapitach lub zdaniach z zachowaniem kontekstu
- **Obsluga tabel** — PyMuPDF gubi strukture tabel (sprawozdania finansowe). Dedykowany parser (Camelot, Unstructured) lub OCR poprawilby ekstrakcje danych tabelarycznych
- **Lepsze modele embeddingowe** — obecny `multilingual-e5-small` jest lekki ale ograniczony. Wiekszy model (np. `e5-large`, OpenAI `text-embedding-3-small`) poprawilby trafnosc retrievalu
- **Testy** — unit testy logiki (prompt builder, chunking) bez API key w CI + testy integracyjne z API sprawdzajace retrieval na pytaniach ze znana lokalizacja odpowiedzi w dokumencie
