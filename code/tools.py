"""
tools.py — Internal tool schema loader and action_taken JSON builder.

Loads the tool definitions from data/api_specs/internal_tools.json,
validates tool calls against the schema, and builds the actions_taken
JSON array that goes into the output CSV.

Key rules (from evaluation criteria):
  - verify_identity MUST precede any destructive action if identity not confirmed
  - tool calls must strictly match the schema (correct params, correct types)
  - invalid tool calls = 0% on Tool Calling dimension
"""

import json
from pathlib import Path
from typing import Optional

from config import API_SPECS_FILE

# ---------------------------------------------------------------------------
# Load tool schemas once at import
# ---------------------------------------------------------------------------
_TOOL_SCHEMAS: dict[str, dict] = {}

def _load_tools() -> None:
    global _TOOL_SCHEMAS
    if _TOOL_SCHEMAS:
        return
    if not API_SPECS_FILE.exists():
        print(f"[Tools] WARNING: tool spec file not found at {API_SPECS_FILE}")
        return
    raw = json.loads(API_SPECS_FILE.read_text(encoding="utf-8"))
    for tool in raw:
        _TOOL_SCHEMAS[tool["name"]] = tool

_load_tools()

AVAILABLE_TOOLS = list(_TOOL_SCHEMAS.keys())

# ---------------------------------------------------------------------------
# Tool description string for LLM prompt context
# ---------------------------------------------------------------------------

def tools_description() -> str:
    """Returns a compact string describing available tools for the LLM prompt."""
    lines = ["Available internal tools (use ONLY these, strictly follow schemas):"]
    for name, schema in _TOOL_SCHEMAS.items():
        props = schema.get("parameters", {}).get("properties", {})
        required = schema.get("parameters", {}).get("required", [])
        param_str = ", ".join(
            f"{p}({'required' if p in required else 'optional'})"
            for p in props
        )
        lines.append(f"  - {name}({param_str}): {schema['description'][:120]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Action builder — construct validated tool call dicts
# ---------------------------------------------------------------------------

def build_action(tool_name: str, **params) -> Optional[dict]:
    """
    Build a single validated tool-call dict.
    Returns None if tool_name is unknown or required params are missing.
    """
    if tool_name not in _TOOL_SCHEMAS:
        return None

    schema = _TOOL_SCHEMAS[tool_name]
    required = schema.get("parameters", {}).get("required", [])
    properties = schema.get("parameters", {}).get("properties", {})

    # Check required params present
    for req in required:
        if req not in params:
            print(f"[Tools] Missing required param '{req}' for tool '{tool_name}'")
            return None

    # Keep only known params
    clean_params = {k: v for k, v in params.items() if k in properties}

    return {"action": tool_name, "parameters": clean_params}


def build_actions_json(actions: list[dict]) -> str:
    """Serialize a list of action dicts to a JSON string (for CSV column)."""
    valid = [a for a in actions if a is not None]
    return json.dumps(valid)


# ---------------------------------------------------------------------------
# LLM output → validated actions
# ---------------------------------------------------------------------------

def parse_and_validate_actions(raw: str) -> str:
    """
    Parse the LLM's actions_taken output (JSON string or list) and validate
    each action against the tool schema. Returns a valid JSON array string.

    Strips invalid tools, missing-param actions, and malformed entries.
    """
    if not raw or not raw.strip():
        return "[]"

    # Try to parse as JSON
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON array
        import re
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                return "[]"
        else:
            return "[]"

    if not isinstance(parsed, list):
        return "[]"

    validated = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        tool_name = item.get("action") or item.get("name") or item.get("tool")
        parameters = item.get("parameters") or item.get("params") or {}

        if not tool_name or tool_name not in _TOOL_SCHEMAS:
            continue

        action = build_action(tool_name, **parameters)
        if action:
            validated.append(action)

    return json.dumps(validated)


# ---------------------------------------------------------------------------
# Escalation shortcut
# ---------------------------------------------------------------------------

def escalate_action(priority: str, department: str, summary: str) -> str:
    """Build a pre-validated escalate_to_human action JSON string."""
    action = build_action(
        "escalate_to_human",
        priority=priority,
        department=department,
        summary=summary[:300],
    )
    return build_actions_json([action] if action else [])


def lock_account_action(user_identifier: str, lock_reason: str) -> str:
    """Build a pre-validated lock_account action JSON string."""
    action = build_action(
        "lock_account",
        user_identifier=user_identifier,
        lock_reason=lock_reason,
    )
    return build_actions_json([action] if action else [])


def verify_identity_action(method: str = "email_otp", target: str = "user") -> str:
    """Build a pre-validated verify_identity action JSON string."""
    action = build_action("verify_identity", method=method, target=target)
    return build_actions_json([action] if action else [])
