# Support Triage Agent — Quickstart

This folder contains the complete, production-ready AI agent for processing support tickets. The agent utilizes an in-memory BM25 retrieval system, deterministic pre-LLM safety heuristics, and parallel processing to handle large ticket batches efficiently.

## Prerequisites

1. **Python 3.12** is recommended.
2. A valid LLM API key. The agent defaults to Groq (`llama-3.3-70b-versatile`), but you can use others if you adapt the `llm_client.py`.

## Setup Instructions

1. **Create and Activate a Virtual Environment:**
   From the repository root (the folder containing the `code/` directory), run:
   ```bash
   python -m venv venv
   
   # Windows:
   venv\Scripts\activate
   
   # macOS/Linux:
   source venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r code/requirements.txt
   ```

3. **Configure the Environment:**
   Create a `.env` file in the repository root and add your API key:
   ```env
   GROQ_API_KEY="gsk_your_key_here"
   # Optional overrides:
   # LLM_PROVIDER="groq"
   # LLM_MODEL="llama-3.3-70b-versatile"
   ```

## Running the Agent

To execute the agent against the test set, ensure your virtual environment is active and run the following command from the **repository root**:

```bash
python code/main.py
```

### Advanced Usage

You can optionally specify input/output paths and the number of parallel workers:

```bash
python code/main.py --input support_tickets/custom_tickets.csv --output support_tickets/custom_output.csv --workers 4
```

*Note: The agent is optimized to run with 8 parallel workers to ensure it processes the 150-ticket hidden eval set within the 3-minute limit. If you encounter API rate limits (HTTP 429), the agent will gracefully fall back to a safe escalation row rather than crashing.*

## Validating the Output

After the agent finishes running, you can verify that the generated CSV strictly conforms to the required 14-column schema:

```bash
python code/validate_output.py
```
*(Ensure your terminal supports UTF-8 encoding if you run into character map errors on Windows).*
