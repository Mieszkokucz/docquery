import anthropic
from dotenv import load_dotenv

from backend.app.config import CHAT_MODEL

load_dotenv()


def ask(messages: list[dict], system: str) -> str:
    """Send messages to Anthropic API and return the text response."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return response.content[0].text
