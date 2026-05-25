"""
llm_client.py — LLM wrapper with temperature=0 for determinism.

Supports Groq (primary). Falls back gracefully on API errors.
Uses response_format=json_object where supported to eliminate parse failures.
"""

import os
import json
import time
import re
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
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
        _client = genai
    elif provider == "bedrock":
        import boto3
        _client = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
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
    retry_delay: float = 3.0,
) -> str:
    """
    Call the configured LLM and return the response text.
    Uses JSON mode on Groq/OpenAI to eliminate truncation parse failures.
    Retries with exponential backoff on rate limit (429) errors.
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
                    response_format={"type": "json_object"},  # KEY FIX: forces valid JSON output
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

            elif provider == "bedrock":
                # Bedrock Converse API (works for Claude 3 on Bedrock)
                messages = [{"role": "user", "content": [{"text": user_prompt}]}]
                system = [{"text": system_prompt}]
                
                response = client.converse(
                    modelId=LLM_MODEL,
                    messages=messages,
                    system=system,
                    inferenceConfig={
                        "maxTokens": LLM_MAX_TOKENS,
                        "temperature": LLM_TEMPERATURE,
                    }
                )
                return response["output"]["message"]["content"][0]["text"]

        except Exception as e:
            err_str = str(e).lower()
            # Rate limit — wait longer before retry
            if "429" in err_str or "rate limit" in err_str or "rate_limit" in err_str:
                wait = retry_delay * (2 ** attempt)  # exponential backoff: 3s, 6s, 12s
                print(f"[LLM] Rate limit hit (attempt {attempt+1}), waiting {wait:.0f}s...")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                print(f"[LLM] Failed after {max_retries} attempts: {e}")
                return ""

    return ""


# ---------------------------------------------------------------------------
# JSON extraction helper — with truncation repair
# ---------------------------------------------------------------------------

def extract_json(text: str) -> Optional[dict]:
    """
    Extract the first JSON object from an LLM response string.
    Handles:
      - Groq JSON mode output (clean JSON)
      - Code-fenced JSON (```json ... ```)
      - Bare JSON with preamble
      - Truncated JSON (attempts bracket-balance repair)
    Returns None only if all strategies fail.
    """
    if not text:
        return None

    # 1. Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # 2. Try full text as-is (fast path — works when JSON mode is active)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Find the first { ... } block (handles preamble text)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        candidate = match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # 4. Attempt truncation repair: find the last complete key-value pair
        #    by walking backwards to find a valid closing brace position
        candidate = _repair_truncated_json(candidate)
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    return None


def _repair_truncated_json(text: str) -> Optional[str]:
    """
    Attempt to repair a truncated JSON object by closing open brackets.
    Strategy: count open braces/brackets and close them.
    """
    # Remove the last incomplete value (find last complete comma-terminated entry)
    # Try stripping from the last comma onwards and closing the object
    last_comma = text.rfind(",")
    last_quote = text.rfind('"')
    last_colon = text.rfind(":")

    if last_comma > 0:
        truncated = text[:last_comma]
    else:
        truncated = text

    # Count open braces and brackets to close
    open_braces   = truncated.count("{") - truncated.count("}")
    open_brackets  = truncated.count("[") - truncated.count("]")

    if open_braces < 0 or open_brackets < 0:
        return None

    repaired = truncated
    repaired += "]" * open_brackets
    repaired += "}" * open_braces

    return repaired if open_braces > 0 else None
