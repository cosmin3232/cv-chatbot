from pathlib import Path

MAX_KNOWLEDGE_CHARACTERS = 12000


def load_knowledge(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise ValueError("CV knowledge is missing. Import and review the documents first.") from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError("CV knowledge could not be read.") from exc
    if not text:
        raise ValueError("CV knowledge is empty.")
    if len(text) > MAX_KNOWLEDGE_CHARACTERS:
        raise ValueError("CV knowledge exceeds 12,000 characters. Review and shorten it first.")
    return text
