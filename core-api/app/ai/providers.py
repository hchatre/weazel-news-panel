"""Model providers. A provider only turns (system, user) text into text. It has no tools and no access to the database, so a
model can never take an action: whatever it returns is a suggestion that a person reads."""
import json
import re

import httpx

from app.config import get_settings


class ProviderError(Exception):
    """Raised for any provider failure. The message is for server logs only and is never returned to the client."""


class MockProvider:
    """Deterministic offline stub. It records every call so tests can assert exactly what would have been sent to a model."""
    name = "mock"
    model = "mock-1"
    calls: list[dict] = []
    fail = False

    def complete(self, system: str, user: str) -> str:
        MockProvider.calls.append({"system": system, "user": user})
        if MockProvider.fail:
            raise ProviderError("simulated provider outage: secret-internal-detail")
        ids = re.findall(r"\[E(\d+)\]", user)
        cites = " ".join(f"[E{i}]" for i in ids[:3])
        if "HALLUCINATE" in user:
            cites += " [E9999]"
        return f"MOCK OUTPUT {cites}".strip()


class HttpProvider:
    def __init__(self, kind: str, base_url: str, model: str, api_key: str, timeout: int, transport: httpx.BaseTransport | None = None):
        self.name, self.kind, self.model = kind, kind, model
        self.base_url, self.api_key, self.timeout, self.transport = base_url.rstrip("/"), api_key, timeout, transport

    def complete(self, system: str, user: str) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.kind == "ollama":
            url, body = f"{self.base_url}/api/chat", {"model": self.model, "messages": messages, "stream": False}
        else:
            url, body = f"{self.base_url}/v1/chat/completions", {"model": self.model, "messages": messages, "temperature": 0.2}
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False, transport=self.transport) as c:  # redirects are never followed
                r = c.post(url, headers=headers, content=json.dumps(body))
            r.raise_for_status()
            data = r.json()
            text = data["message"]["content"] if self.kind == "ollama" else data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"{type(e).__name__}") from e  # no body, no URL, no key in the message
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("empty response")
        return text


def get_provider():
    s = get_settings()
    if s.AI_PROVIDER == "none":
        return None
    if s.AI_PROVIDER == "mock":
        return MockProvider()
    return HttpProvider(s.AI_PROVIDER, s.AI_BASE_URL, s.AI_MODEL, s.AI_API_KEY, s.AI_TIMEOUT_SECONDS)
