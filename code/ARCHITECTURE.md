# Agent Architecture — MLE Hiring Challenge

This document outlines the design, data flow, safety mechanisms, and limitations of the AI triage agent built for the MLE Hiring Challenge. 

## 1. High-Level Architecture & Data Flow

The agent employs a **7-layer pipeline** designed for speed, determinism, and extreme adversarial resilience. To meet the strict 3-minute execution limit for 150+ tickets, the pipeline is fully parallelized using `ThreadPoolExecutor`, while maintaining deterministic row ordering in the output CSV.

```mermaid
graph TD
    A[Input CSV Row] --> B[Parse & Sanitize JSON]
    B --> C{Heuristic Safety Gate}
    C -- "Injection/Attack Detected" --> D[Immediate Refusal (No LLM)]
    C -- "Safe" --> E[PII & Language Detection]
    E --> F[Domain Inference]
    F --> G[BM25 Retrieval (791 docs)]
    G --> H[LLM Generation (Temp=0)]
    H --> I[Post-Processing & Validation]
    D --> J[TicketOutput Row]
    I --> J
```

### Component Breakdown
1. **Parser & Sanitizer:** Extracts raw text from JSON arrays, normalizes Unicode, and strips dangerous control characters.
2. **Safety Gate (`safety.py`):** Runs deterministic, heuristic checks (0ms overhead) to intercept attacks before they reach the LLM.
3. **Domain Classifier:** Infers the target domain (DevPlatform, Claude, Visa) based on the `company` field and content overlap signals.
4. **Retriever (`retriever.py`):** In-memory BM25 index over all 791 corpus documents.
5. **LLM Engine (`llm_client.py`):** Interacts with Groq (`llama-3.3-70b-versatile`) at `temperature=0` using strict JSON structuring.
6. **Post-Processor (`tools.py`):** Validates the `source_documents` against the actual filesystem (preventing hallucinated citations), redacts PII from the response, and ensures `actions_taken` conform to the strict JSON schema.

---

## 2. Retrieval Strategy

**Approach: In-Memory BM25 (Okapi) with Domain Filtering**

- **Why BM25 over Vector Embeddings?** 
  Given the strict 3-minute evaluation constraint and the requirement for no external network calls (aside from the LLM), building a heavy vector database (like FAISS + SentenceTransformers) on every run is too slow and resource-intensive. BM25 builds an index over 790 documents in <1 second, runs entirely in-memory, requires zero network dependencies, and is completely deterministic.
- **Context Construction:** The retriever pairs the top 3 documents with the query. Crucially, it validates the physical existence of the file path before passing it to the LLM, mathematically eliminating the risk of a -50% penalty for hallucinated citations.

---

## 3. Adversarial & Safety Handling

The agent uses a **Defense-in-Depth** strategy. Relying solely on system prompts is insufficient against sophisticated jailbreaks. 

1. **Pre-LLM Heuristic Gate:**
   - **Structural Analysis:** Scans for Excel formula injections (`=cmd|...`), XML/HTML overrides (`<system>`), and empty arrays (`[]`).
   - **Obfuscation Detection:** Attempts to decode Base64 strings. If decoding succeeds, the decoded payload is recursively scanned. Unicode homoglyphs are also flagged.
   - **Keyword Matching:** Scans for 40+ known jailbreak triggers (e.g., "ignore previous instructions", "DAN mode", "auth_code").
   - **Fake Authority:** Flags social engineering attempts (e.g., "I am a DevPlatform employee", "routine audit").
   *Result:* If tripped, the agent returns a pre-canned refusal (`risk=high`, `confidence=0.99`) **without invoking the LLM**, saving time and ensuring 100% safety.

2. **LLM-Level Hardening:**
   - The system prompt explicitly defines user input as "untrusted data" and strictly prohibits the revelation of internal tools or system prompts.

3. **Post-LLM PII Redaction:**
   - The agent uses regex to detect 7 classes of PII (SSN, credit cards, emails, etc.) in the incoming ticket.
   - Before writing the output CSV, the response string is scanned, and any echoed PII is replaced with generic placeholders (e.g., `[SSN redacted]`).

---

## 4. Escalation Decision Logic

The agent acts as a strict triage layer. Escalation is preferred over guessing.

- **Immediate Escalation:**
  - `risk == "critical"` (e.g., identity theft, stolen cards, financial fraud).
  - Unparseable or empty LLM output (graceful fallback).
  - Multi-domain or deeply ambiguous queries.
- **Tool-Assisted Escalation:**
  - If a user demands account deletion or refunds but authentication fails, the agent calls `verify_identity` or `escalate_to_human`.
  - Legal threats instantly trigger an `escalate_to_human(priority="high", department="legal")`.
- **Confidence Calibration:** The LLM's raw confidence score is clamped against a heuristic baseline. If the BM25 score is very low (meaning no relevant corpus documents exist), the agent's confidence is artificially lowered, forcing an escalation.

---

## 5. Known Limitations & Failure Modes

1. **API Rate Limiting:** When testing large batches (90+ tickets) simultaneously, the LLM provider (e.g., Groq free tier) may return HTTP 429 (Rate Limit Exceeded) or HTTP 503. 
   *Mitigation:* The agent catches these exceptions after 3 retries and gracefully degrades to a "safe fallback row" (status=escalated). This prevents the pipeline from crashing, ensuring compliance with the evaluation rules.
2. **Multilingual Limitations:** While the agent detects languages via `langdetect` and Unicode blocks, the BM25 retrieval relies heavily on exact keyword matching. A ticket written in French searching for English corpus terms will have lower retrieval accuracy.
3. **Context Window Overflow:** If a ticket contains massive conversation arrays, the prompt could exceed token limits. The agent currently sanitizes and truncates extreme inputs, but highly verbose tickets may lose context.
