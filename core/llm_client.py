"""
Simple local LLM client for Sovereign Signals V6.

This version talks to an Ollama instance running on the same machine.
Default model: gemma3:12b (but you can change it below).

Usage:
    from core.llm_client import generate_text
    text = generate_text("Explain block 840,000...")
"""

from __future__ import annotations

import os
from typing import List, Dict, Any

import requests

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

from .config import get_config

_cfg = get_config()

# Base URL for Ollama. Change this if your Ollama server lives elsewhere.
OLLAMA_URL = _cfg.get("ollama_base_url", "http://localhost:11434")

# Default model name. You can override with env var SOV_OLLAMA_MODEL.
# Examples: "gemma3:12b", "llama3:8b", "qwen2.5:7b"
OLLAMA_MODEL = _cfg.get("ollama_model", "gemma3:12b")

# Reasonable default upper bound; Ollama ignores if model has smaller context.
DEFAULT_MAX_TOKENS = 320


class LLMClientError(RuntimeError):
    """Custom error for LLM client failures."""


# ---------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------

def _post_chat(messages: List[Dict[str, Any]],
               max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """
    Low-level helper: send a chat-style request to Ollama and return the text.
    """
    url = f"{OLLAMA_URL.rstrip('/')}/api/chat"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        # Some models ignore "num_predict"; included for best-effort control.
        "options": {
            "num_predict": max_tokens,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=120)
    except Exception as exc:  # noqa: BLE001
        raise LLMClientError(f"Failed to reach Ollama at {url}: {exc}") from exc

    if resp.status_code != 200:
        raise LLMClientError(
            f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"
        )

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise LLMClientError(f"Invalid JSON from Ollama: {exc}") from exc

    message = data.get("message") or {}
    content = message.get("content", "")
    if not isinstance(content, str):
        raise LLMClientError("Ollama response did not contain string content")

    return content.strip()


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def generate_text(prompt: str,
                  max_tokens: int = DEFAULT_MAX_TOKENS,
                  system_prompt: str | None = None) -> str:
    """
    High-level helper: send a single user prompt and return the model's reply.

    This is the function imported by other modules:
        from core.llm_client import generate_text
    """
    messages: List[Dict[str, Any]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    return _post_chat(messages, max_tokens=max_tokens)


def health_check() -> bool:
    """
    Quick check that Ollama is reachable and the model loads.

    Returns True if a tiny probe request succeeds, False otherwise.
    """
    try:
        _ = generate_text(
            "Reply with the single word: OK",
            max_tokens=4,
            system_prompt="You are a health-check probe.",
        )
        return True
    except Exception:
        return False


class LLMClient:
    """Simple client wrapper for narrative.py"""

    def available(self) -> bool:
        return health_check()

    def generate_text(self, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, system_prompt: str | None = None) -> str:
        return generate_text(prompt, max_tokens, system_prompt)


def get_client() -> LLMClient:
    return LLMClient()
