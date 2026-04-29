# DocQuery — asystent RAG do raportu rocznego BGK

Aplikacja umozliwiajaca zadawanie pytan o raport roczny BGK w jezyku naturalnym. System odpowiada na podstawie tresci dokumentu, cytujac konkretne strony. Gdy informacji brak w raporcie — odmawia odpowiedzi zamiast halucynowac.

## Stack technologiczny

| Komponent | Technologia | Dlaczego |
|---|---|---|
| Backend API | FastAPI | Szybki, typowany, auto-dokumentacja (Swagger) |
| Frontend | Streamlit | Wbudowane komponenty chatowe, zero JS |
| Ekstrakcja PDF | Claude Vision API (offline, cache JSON) | Wydobywa tekst, tabele i infografiki ze strukturą rozdziału/sekcji — działa tylko offline, nie jest uruchamiany przez backend na żywo |
| Baza wektorowa | ChromaDB (in-memory) | Zero konfiguracji, wystarczy dla demo |
| Embeddingi | OpenAI `text-embedding-3-small` (przez API) | Wysoka jakość, brak lokalnego stosu PyTorch |
| LLM | Claude Sonnet 4.6 (vision + chat) | W eksperymencie okazał się najlepszy  test_vision_extraction_on_gt_joined.ipynb |
| Konteneryzacja | Docker Compose | Jednokomendowy setup |

## Architektura

### Indeksowanie (startup backendu)

Backend nie przetwarza PDF na żywo. Korzysta z prekomputowanego cache, wygenerowanego offline przez Claude Vision API.

```
data/extraction_v2/*.json (cache vision) --> chunker_v2 (paragraph/table/infographic)
    --> OpenAI embeddings (text-embedding-3-small) --> ChromaDB (in-memory)
```

### Obsługa zapytania

```
Pytanie użytkownika
    |
    v
Retrieval: search_v2 → top-5 chunków z ChromaDB (cosine, OpenAI embeddings)
    |
    v
build_prompt_v2: kontekst (chunki z metadanymi rozdziału/sekcji/typu)
                 + historia konwersacji + pytanie
    |
    v
Claude Sonnet 4.6 → odpowiedź z cytatami [Strona X], [Strony X-Y],
                    [Tabela, s. X], [Infografika, s. X]
    |
    v
parse_citations + match_sources → ChatResponse{answer, sources[]}
```

Backend utrzymuje historię konwersacji per `session_id` (in-memory). Historia jest przekazywana do LLM, lecz **retrieval działa wyłącznie na podstawie ostatniego pytania** — krótkie follow-upy bez samodzielnego kontekstu mogą trafiać w nieodpowiednie chunki.

## Uruchomienie

### Wymagania

- Docker + Docker Compose
- Klucz API Anthropic (chat + vision)
- Klucz API OpenAI (embeddingi)
- Cache vision wygenerowany w `data/extraction_v2/` (pre-requisite startu backendu)

### Docker (zalecane)

```bash
git clone <repo-url>
cd docquery
cp .env.example .env
# Wpisz ANTHROPIC_API_KEY i OPENAI_API_KEY w pliku .env
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

## Zmienne środowiskowe

| Zmienna | Wymagana | Opis |
|---|---|---|
| `ANTHROPIC_API_KEY` | Tak | Klucz API do Claude (chat + ekstrakcja vision) — brak nie blokuje startu, ale spowoduje błąd przy pierwszym pytaniu |
| `OPENAI_API_KEY` | Tak | Klucz API do OpenAI (embeddingi `text-embedding-3-small`) |
| `BACKEND_URL` | Nie | Adres backendu dla frontendu (domyślnie `http://localhost:8000`) |

Plik `.env.example` zawiera wzór konfiguracji.

## Możliwe usprawnienia

- **Query expansion (retrieval świadomy kontekstu)** — follow-up pytania ("a co w 2023?") trafiają do retrieval jako gołe zdanie bez historii; ChromaDB nie wie, o czym rozmowa. Rozwiązanie: mały/tani model (Haiku 4.5 lub GPT-4o-mini) przegląda ostatnie N wiadomości i przepisuje zapytanie na samodzielne zdanie przed wyszukiwaniem. Nowy moduł: `backend/app/retrieval/query_rewriter.py`, wywoływany w `routes.py` przed `search_v2`.

- **Porównanie modeli** — Sonnet 4.6 wygrał test ekstrakcji vision, ale do zadania chat (retrieval + odpowiedź) może istnieć tańsza/szybsza alternatywa. Do porównania na eval secie (`data/eval/bgk_2024_qa_eval.json`): Sonnet 4.6 vs Haiku 4.5 vs GPT-4o-mini. Metryki: jakość odpowiedzi (LLM-as-judge), trafność cytowań, koszt per pytanie, mediana latencji. Notebook: `notebooks/model_comparison.ipynb`.

- **Eval set** — plik `data/eval/bgk_2024_qa_eval.json` zawiera 14 pytań (single-hop, PL). Ewaluacja retrieval jest już zaimplementowana jako test integracyjny `backend/tests/retrieval/test_eval_retrieval.py` (marker `@pytest.mark.integration`). Brakuje osobnego skryptu mierzącego trafność końcowych odpowiedzi LLM.

- **Streaming odpowiedzi** — obecnie odpowiedź wraca w całości; streaming poprawiłby UX.

- **Persystencja indeksu** — ChromaDB działa in-memory, re-indeksacja przy każdym restarcie (z cache JSON). Dla większych dokumentów: tryb `PersistentClient`.

- **Persystencja historii konwersacji** — `history.py` trzyma sesje w słowniku; reset przy restarcie. Redis / PostgreSQL zachowałyby kontekst między restartami.

- **MCP server** — wyeksponowanie DocQuery jako serwera [MCP](https://modelcontextprotocol.io) pozwoliłoby narzędziom jak Claude Desktop lub Cursor odpytywać raport BGK bezpośrednio, bez UI przeglądarki. Jeden tool: `query_bgk_report(question: str) -> str`. Implementacja: `backend/app/mcp_server.py` (biblioteka `fastmcp` lub oficjalne `mcp` SDK Anthropic).
