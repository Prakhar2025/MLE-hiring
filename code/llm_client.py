"""
llm_client.py — LLM wrapper with temperature=0 for determinism.

Supports Groq (primary). Falls back gracefully on API errors.
All calls use structured JSON output mode to avoid parsing failures.
"""

import os
import json
import time
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from config import LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS

# ---------------------------------------------------------------------------
# Build the client once at import time
# ---------------------------------------------------------------------------
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    provider = LLM_PROVIDER.lower()

    if provider == "groq":
        from groq import Groq
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    elif provider == "openai":
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    elif provider == "anthropic":
        from anthropic import Anthropic
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    elif provider == "google":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        _client = genai
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")

    return _client


# ---------------------------------------------------------------------------
# Core call function
# ---------------------------------------------------------------------------

def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> str:
    """
    Call the configured LLM and return the response text.
    Retries on transient errors up to max_retries times.
    Always uses temperature=0 for determinism.
    Returns empty string on unrecoverable error (caller handles fallback).
    """
    provider = LLM_PROVIDER.lower()
    client = _get_client()

    for attempt in range(max_retries):
        try:
            if provider in ("groq", "openai"):
                response = client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=LLM_TEMPERATURE,
                    max_tokens=LLM_MAX_TOKENS,
                )
                return response.choices[0].message.content or ""

            elif provider == "anthropic":
                from anthropic import Anthropic
                response = client.messages.create(
                    model=LLM_MODEL,
                    max_tokens=LLM_MAX_TOKENS,
                    temperature=LLM_TEMPERATURE,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text or ""

            elif provider == "google":
                import google.generativeai as genai
                model = genai.GenerativeModel(
                    model_name=LLM_MODEL,
                    system_instruction=system_prompt,
                )
                resp = model.generate_content(
                    user_prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=LLM_TEMPERATURE,
                        max_output_tokens=LLM_MAX_TOKENS,
                    ),
                )
                return resp.text or ""

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
            else:
                print(f"[LLM] Failed after {max_retries} attempts: {e}")
                return ""

    return ""


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def extract_json(text: str) -> Optional[dict]:
    """
    Extract the first JSON object from an LLM response string.
    Handles code-fenced JSON (```json ... ```) and bare JSON.
    Returns None if no valid JSON found.
    """
    if not text:
        return None

    # Strip markdown code fences
    import re
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # Try full text first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find first {...} block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None
