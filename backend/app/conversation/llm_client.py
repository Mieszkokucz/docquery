import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-20250514"


def ask(messages: list[dict], system: str) -> str:
    """Send messages to Anthropic API and return the text response."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return response.content[0].text
