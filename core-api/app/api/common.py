import re

from fastapi import HTTPException

NOT_FOUND = HTTPException(404, "Not found")


def clean_text(value: str | None, max_len: int, *, multiline: bool = False) -> str:
    """Strips control characters and trims. Output encoding is the frontend's job (it renders text, never HTML);
    we do not HTML-escape stored data because that would corrupt it."""
    if value is None:
        return ""
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()
    if not multiline:
        value = re.sub(r"\s*[\r\n\t]+\s*", " ", value)
    return value[:max_len]


def safe_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if len(url) > 500 or not re.fullmatch(r"https?://[\w\-._~:/?#\[\]@!$&()*+,;=%]+", url):
        raise HTTPException(422, "Invalid URL (only plain http/https addresses are accepted)")
    return url


def snippet(text: str, q: str, width: int = 80) -> str:
    i = text.lower().find(q.lower())
    if i < 0:
        return text[: width * 2]
    start = max(0, i - width)
    return ("..." if start else "") + text[start : i + len(q) + width] + ("..." if i + len(q) + width < len(text) else "")


def like_pattern(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
