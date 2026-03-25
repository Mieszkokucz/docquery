sessions: dict[str, list[dict]] = {}


def add_message(session_id: str, role: str, content: str) -> None:
    if session_id not in sessions:
        sessions[session_id] = []
    sessions[session_id].append({"role": role, "content": content})


def get_history(session_id: str) -> list[dict]:
    return list(sessions.get(session_id, []))
