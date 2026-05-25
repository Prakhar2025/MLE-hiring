"""
safety.py — Pre-LLM safety layer (deterministic, no LLM calls).

1. detect_injection()      — heuristic injection/jailbreak detection
2. detect_pii()            — regex PII detection
3. redact_pii_from_response() — prevent PII echo in responses
4. detect_language()       — ISO 639-1 language code
5. sanitize_text()         — strip control chars, decode base64
6. is_empty_or_trivial()   — empty/emoji/urls-only detection
7. assess_risk_from_content() — heuristic risk level
"""

import re
import base64
import unicodedata
from typing import Optional

try:
    from langdetect import detect as _ld_detect, LangDetectException
    _LANGDETECT_OK = True
except ImportError:
    _LANGDETECT_OK = False

from config import (
    INJECTION_KEYWORDS, INJECTION_PATTERNS_STRUCTURAL,
    FAKE_AUTHORITY_PHRASES, PII_PATTERNS,
)

# --- Compile regex once at import ---
_PII_RE     = {k: re.compile(v, re.IGNORECASE) for k, v in PII_PATTERNS.items()}
_STRUCT_RE  = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in INJECTION_PATTERNS_STRUCTURAL]
_HOMOGLYPH  = re.compile(r"[\u0400-\u04FF\u0370-\u03FF]")
_URL_RE     = re.compile(r"https?://\S+", re.IGNORECASE)


# ===========================================================================
# 1. INJECTION DETECTION
# ===========================================================================

def detect_injection(text: str) -> tuple[bool, str]:
    """Returns (is_injection, reason_string)."""
    if not text or not text.strip():
        return False, ""
    lower = text.lower()

    # a) Base64 decode + rescan
    decoded = _try_base64(text)
    if decoded:
        ok, reason = _kw_scan(decoded.lower())
        if ok:
            return True, f"Base64 injection: {reason}"

    # b) Keywords
    ok, reason = _kw_scan(lower)
    if ok:
        return True, reason

    # c) Structural (HTML tags, Excel formulas)
    for pat in _STRUCT_RE:
        m = pat.search(text)
        if m:
            return True, f"Structural injection: '{m.group()}'"

    # d) Fake authority
    for phrase in FAKE_AUTHORITY_PHRASES:
        if phrase in lower:
            return True, f"Fake authority: '{phrase}'"

    # e) Homoglyph + injection keywords
    if _HOMOGLYPH.search(text):
        if any(kw in lower for kw in ["ignore", "override", "disregard"]):
            return True, "Homoglyph smuggling with injection keywords"

    return False, ""


def _kw_scan(lower_text: str) -> tuple[bool, str]:
    for kw in INJECTION_KEYWORDS:
        if kw in lower_text:
            return True, f"Keyword: '{kw}'"
    return False, ""


def _try_base64(text: str) -> Optional[str]:
    candidates = [text.strip()] + text.strip().split()[-1:]
    for c in candidates:
        if re.match(r'^[A-Za-z0-9+/=\s]{20,}$', c):
            try:
                d = base64.b64decode(c + "==").decode("utf-8", errors="ignore")
                if len(d) > 5:
                    return d
            except Exception:
                pass
    return None


# ===========================================================================
# 2. PII DETECTION + REDACTION
# ===========================================================================

_PII_PLACEHOLDERS = {
    "credit_card": "[card ending XXXX]",
    "ssn":         "[SSN redacted]",
    "email":       "[email on file]",
    "phone_us":    "[phone on file]",
    "phone_intl":  "[phone on file]",
    "address":     "[address on file]",
    "dob":         "[date of birth on file]",
}


def detect_pii(text: str) -> tuple[bool, list[str]]:
    """Returns (found, list_of_pii_types)."""
    if not text:
        return False, []
    found = [k for k, pat in _PII_RE.items() if pat.search(text)]
    return bool(found), found


def redact_pii_from_response(response: str) -> str:
    """Replace any PII patterns in the response with generic placeholders."""
    for pii_type, pat in _PII_RE.items():
        response = pat.sub(_PII_PLACEHOLDERS.get(pii_type, "[redacted]"), response)
    return response


# ===========================================================================
# 3. LANGUAGE DETECTION
# ===========================================================================

def detect_language(text: str) -> str:
    """Returns ISO 639-1 code. Falls back to 'en'."""
    if not text or len(text.strip()) < 20:
        return "en"
    clean = sanitize_text(text)[:500]
    if _LANGDETECT_OK:
        try:
            lang = _ld_detect(clean)
            return lang or "en"
        except LangDetectException:
            pass
    return _heuristic_lang(text)


def _heuristic_lang(text: str) -> str:
    total = max(len(text), 1)
    cjk     = len(re.findall(r'[\u4e00-\u9fff\u3040-\u30ff]', text)) / total
    arabic  = len(re.findall(r'[\u0600-\u06FF]', text)) / total
    cyrillic= len(re.findall(r'[\u0400-\u04FF]', text)) / total
    lat_ext = len(re.findall(r'[àáâãäåæçèéêëìíîïðÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐ]', text)) / total
    if cjk > 0.1:      return "zh"
    if arabic > 0.1:   return "ar"
    if cyrillic > 0.1: return "ru"
    if lat_ext > 0.05: return "fr"
    return "en"


# ===========================================================================
# 4. TEXT SANITISATION
# ===========================================================================

def sanitize_text(text: str) -> str:
    """Remove null bytes and dangerous control chars. Normalize Unicode."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text


# ===========================================================================
# 5. EDGE CASE DETECTION
# ===========================================================================

def is_empty_or_trivial(text: str) -> bool:
    """True for empty arrays, whitespace-only, emoji-only, or URLs-only."""
    if not text or text.strip() in ("", "[]", "[ ]"):
        return True
    clean = sanitize_text(text).strip()
    no_emoji = "".join(c for c in clean if unicodedata.category(c) != "So").strip()
    if len(no_emoji) < 5:
        return True
    no_urls = _URL_RE.sub("", no_emoji).strip()
    return len(no_urls) < 5


# ===========================================================================
# 6. RISK ASSESSMENT (heuristic, pre-LLM)
# ===========================================================================

def assess_risk_from_content(text: str, pii_types: list[str], is_injection: bool) -> str:
    """Returns 'low' | 'medium' | 'high' | 'critical'."""
    if is_injection:
        return "high"
    lower = text.lower()
    if (any(s in lower for s in [
            "identity theft", "identity stolen", "account hacked",
            "unauthorized transaction", "fraudulent charge", "stolen card",
            "credit card fraud", "ssn", "social security"])
            or "credit_card" in pii_types or "ssn" in pii_types):
        return "critical"
    if any(s in lower for s in [
            "lawsuit", "legal action", "lawyer", "attorney", "class action",
            "gdpr", "hipaa", "data breach", "security vulnerability",
            "account takeover", "privacy breach", "bug bounty"]):
        return "high"
    if any(s in lower for s in [
            "reset password", "can't log in", "locked out",
            "subscription", "cancel", "blocked card", "stranded", "refund"]):
        return "medium"
    return "low"
