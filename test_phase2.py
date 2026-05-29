import sys
sys.path.insert(0, 'code')
from dotenv import load_dotenv
load_dotenv()

from tools import AVAILABLE_TOOLS, parse_and_validate_actions
from llm_client import _get_client
from agent import _extract_conversation_text, _infer_domain

# Test tool schema
print("Tools:", AVAILABLE_TOOLS)

# Test text extraction
raw = '[{"role": "user", "content": "I lost my Visa card in Tokyo"}]'
text = _extract_conversation_text(raw)
print("Extracted:", text[:80])

# Test empty
text2 = _extract_conversation_text("[]")
print("Empty:", repr(text2))

# Test domain
dom = _infer_domain("None", "my visa card was stolen in japan")
print("Domain:", dom)

# Test LLM client
client = _get_client()
print("LLM client:", type(client).__name__)

# Test action validation
import json
raw_action = json.dumps([{"action": "escalate_to_human", "parameters": {"priority": "high", "department": "security", "summary": "test"}}])
validated = parse_and_validate_actions(raw_action)
print("Validated action:", validated)

print("Phase 2 ALL GOOD")
