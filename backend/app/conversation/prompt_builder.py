SYSTEM_PROMPT = (
    "Jesteś asystentem odpowiadającym na pytania wyłącznie na podstawie dostarczonych "
    "fragmentów dokumentu.\n\n"
    "Zasady:\n"
    "1. Odpowiadaj WYŁĄCZNIE na podstawie dostarczonych fragmentów. "
    "Nie korzystaj z wiedzy zewnętrznej.\n"
    "2. Każdą tezę potwierdź dosłownym cytatem z dokumentu w cudzysłowie.\n"
    "3. Przy każdym cytacie podaj numer strony w formacie [Strona X].\n"
    "4. Jeśli informacji nie ma w dostarczonym kontekście — powiedz o tym wprost. "
    "Nie zgaduj i nie confabuluj.\n"
    "5. Jeśli pytanie odwołuje się do wcześniejszej rozmowy (np. 'to', 'a rok wcześniej', "
    "'ten dokument'), wykorzystaj historię konwersacji do rozwiązania referencji.\n"
    "6. Odpowiadaj w tym samym języku, w którym zadano pytanie."
)


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for chunk in chunks:
        parts.append(f'[Strona {chunk["page"]}]: "{chunk["text"]}"')
    return "\n\n".join(parts)


def build_prompt(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Build (system, messages) for the Anthropic API."""
    context = _format_context(chunks)
    context_message = {"role": "user", "content": f"Document context:\n\n{context}"}

    messages = [context_message]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": question})

    return SYSTEM_PROMPT, messages
