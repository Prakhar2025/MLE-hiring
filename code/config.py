"""
config.py — Global constants, paths, and enum definitions.
All other modules import from here. Never hardcode paths elsewhere.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(os.getenv("REPO_ROOT", Path(__file__).parent.parent)).resolve()
DATA_DIR = REPO_ROOT / "data"
TICKETS_DIR = REPO_ROOT / "support_tickets"
INPUT_CSV = TICKETS_DIR / "support_tickets.csv"
OUTPUT_CSV = TICKETS_DIR / "output.csv"
API_SPECS_FILE = DATA_DIR / "api_specs" / "internal_tools.json"

DOMAIN_DIRS = {
    "DevPlatform": DATA_DIR / "devplatform",
    "Claude":      DATA_DIR / "claude",
    "Visa":        DATA_DIR / "visa",
}

# ---------------------------------------------------------------------------
# LLM Settings
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
LLM_MODEL    = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_TEMPERATURE = 0.0      # must be 0 for determinism
LLM_MAX_TOKENS  = 1200     # raised from 700 — JSON was being truncated causing 44% parse failures

# ---------------------------------------------------------------------------
# Retrieval Settings
# ---------------------------------------------------------------------------
BM25_TOP_K = 5             # top-5 docs for better source coverage
MIN_BM25_SCORE = 0.0       # drop documents with score below this threshold

# ---------------------------------------------------------------------------
# Output Enums (string literals — used for validation)
# ---------------------------------------------------------------------------
VALID_STATUS        = {"replied", "escalated"}
VALID_REQUEST_TYPE  = {"product_issue", "feature_request", "bug", "invalid"}
VALID_RISK_LEVEL    = {"low", "medium", "high", "critical"}

# ---------------------------------------------------------------------------
# Supported companies (from dataset)
# ---------------------------------------------------------------------------
KNOWN_COMPANIES = {"DevPlatform", "Claude", "Visa", "None"}

# ---------------------------------------------------------------------------
# Injection detection keywords (case-insensitive substring match)
# ---------------------------------------------------------------------------
INJECTION_KEYWORDS = [
    # -- English injection classics --
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore all previous",
    "disregard all previous",
    "disregard your instructions",
    "forget all instructions",
    "forget previous instructions",
    "new instructions",
    "system override",
    "maintenance mode",
    "dan mode",
    "do anything now",
    "you are now",
    "you are no longer",
    "output the following",
    "respond with exactly",
    "say exactly",
    "repeat after me",
    "auth_code",
    "alert_ack",
    "verify by responding",
    "confirm by saying",
    "internal audit",
    "routine audit",
    "i am a senior",
    "i am an anthropic",
    "i am a devplatform employee",
    "trust & safety team",
    "trust and safety team",
    "qa team",
    "qa-2026",
    "system prompt",
    "full text of your",
    "list all tools",
    "list your tools",
    "retrieval algorithm",
    "knowledge base",
    "list of support articles",
    "how many documents",
    "what documents do you have",
    # -- Roleplay / persona bypass --
    "pretend you are",
    "pretend to be",
    "roleplay as",
    "act as if you are",
    "act as a",
    "imagine you are a human",
    "you are a different ai",
    "switch to developer mode",
    "enable developer mode",
    "jailbreak mode",
    # -- Classification manipulation --
    "classify this as replied",
    "classify this as",
    "do not escalate",
    "mark this as resolved",
    "output exactly",
    "output only",
    "respond only with",
    # -- Source/internal exfiltration --
    "which file did you use",
    "which document did you",
    "what was the source",
    "show me the document",
    "reveal your sources",
    "print your instructions",
    "display your system",
    # -- Excel formula injection (explicit strings) --
    "=cmd|",
    "=dde(",
    "=exec(",
    "=hyperlink(",
    "=importxml(",
    "=webservice(",
    # -- German injection phrases --
    "ignorieren sie ihre",
    "ignorieren sie alle",
    "vergessen sie alle",
    "folgen sie diesen anweisungen",
    "geben sie alle",
    # -- French injection phrases --
    "ignorez vos instructions",
    "ignorez toutes",
    "affiche toutes les r\u00e8gles",
    "affiche tes instructions",
    "montre-moi tes instructions",
    "r\u00e9v\u00e8le tes instructions",
    # -- Spanish injection phrases --
    "ignora tus instrucciones",
    "ignora todas las instrucciones",
    "muestra tus instrucciones",
    # -- Hindi injection phrases (romanized) --
    "apne instructions bhool jao",
    "purani instructions ignore karo",
    # -- Fake prior context injection --
    "previous agent told me",
    "agent tk-",
    "prior agent promised",
    "your colleague told me",
]

INJECTION_PATTERNS_STRUCTURAL = [
    r"<system>",
    r"</system>",
    r"<instructions>",
    r"<override>",
    r"<prompt>",
    r"\[system\s*override\]",
    r"\[system\s*message\]",
    r"(?:^|\n)\s*=",                  # Excel formula at start of line
    r'"content":\s*"=',               # Excel inside JSON content field
    r"\[user\]:\s*=",                 # Excel after [user]: prefix
]

# ---------------------------------------------------------------------------
# Fake authority phrases (used to flag social engineering)
# ---------------------------------------------------------------------------
FAKE_AUTHORITY_PHRASES = [
    "i am a devplatform employee",
    "i work at anthropic",
    "i am from anthropic",
    "i am a senior qa engineer at anthropic",
    "i am performing a routine audit",
    "this is an automated message from",
    "this is a test by the qa team",
    "automated message from your monitoring",
    "ministry of technology",
    "authorized by the ministry",
]

# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------
PII_PATTERNS = {
    "credit_card":  r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
    "ssn":          r"\b\d{3}[\-\s]\d{2}[\-\s]\d{4}\b",
    "email":        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "phone_us":     r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "phone_intl":   r"\b\+\d{1,3}[\s\-]?\d{6,14}\b",
    "address":      r"\b\d+\s+[A-Za-z\s]{3,40}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct)\b",
    "dob":          r"\b\d{2}/\d{2}/\d{4}\b",
}

# ---------------------------------------------------------------------------
# Confidence scoring signals
# ---------------------------------------------------------------------------
HIGH_CONFIDENCE_FLOOR   = 0.90   # strong corpus match, clear intent
MEDIUM_CONFIDENCE_FLOOR = 0.70   # partial match or ambiguous
LOW_CONFIDENCE_FLOOR    = 0.45   # no corpus match or multiple conflicts
INJECTION_CONFIDENCE    = 0.99   # very certain it's adversarial
