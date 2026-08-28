"""Shared model wiring.

One place decides which LLM every team uses. Teams never construct a model
themselves, so swapping provider is a single-file change.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

__all__ = ["DEFAULT_BASE_URL", "DEFAULT_MODEL", "build_model", "load_env"]

# Kimi's coding-plan endpoint. Deliberately not api.moonshot.ai: a
# kimi-for-coding key is rejected there with HTTP 401.
DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
DEFAULT_MODEL = "kimi-for-coding"

_PREFIX = "KIMI_"


def load_env() -> None:
    """Load KIMI_* from the nearest .env, walking up from cwd, then $HOME.

    No dotenv dependency, and no path baked in. KIMI_ENV_FILE overrides.
    """
    if os.environ.get("KIMI_API_KEY"):
        return
    candidates: list[Path] = []
    if override := os.environ.get("KIMI_ENV_FILE"):
        candidates.append(Path(override))
    candidates += [p / ".env" for p in (Path.cwd(), *Path.cwd().parents)]
    candidates.append(Path.home() / ".env")

    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith(_PREFIX):
                os.environ.setdefault(key, value.strip().strip("\"'"))
        if os.environ.get("KIMI_API_KEY"):
            return


def build_model() -> ChatOpenAI:
    """The shared chat model.

    Temperature is left unset on purpose: kimi-for-coding rejects any value
    but 1, so passing 0 fails the request with HTTP 400.
    """
    load_env()
    key = os.environ.get("KIMI_API_KEY")
    if not key:
        raise RuntimeError(
            "KIMI_API_KEY is not set and no .env containing it was found. "
            "Set KIMI_API_KEY, or point KIMI_ENV_FILE at the file holding it."
        )
    return ChatOpenAI(
        model=os.environ.get("KIMI_MODEL", DEFAULT_MODEL),
        api_key=SecretStr(key),
        base_url=os.environ.get("KIMI_BASE_URL", DEFAULT_BASE_URL),
        timeout=180,
        max_retries=3,
    )
