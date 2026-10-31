"""LLM client. Uses OpenRouter if OPENROUTER_API_KEY is set, otherwise an offline deterministic stub.
Tests and the demo always run offline. No key is included in this repo.
"""
import json
import os
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def enabled() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY")) and os.environ.get("DTC_OFFLINE", "1") != "1"


def complete(system: str, user: str, fallback: str) -> str:
    """Return model text, or `fallback` when running offline."""
    if not enabled():
        return fallback
    body = json.dumps({
        "model": os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=body, headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception:  # network/model failure falls back to the safe template
        return fallback
