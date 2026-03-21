# Agent Search

A local Python assistant powered by Ollama with optional web augmentation.

The project uses a single, stateless pipeline in `ollama_web_search.py`:

- Decide whether search is needed
- Generate a query
- Fetch results through a 3-tier fallback chain
- Select best URL
- Fetch and validate context
- Answer with streamed output

## Features

- Local LLM chat via Ollama
- One-shot and interactive chat modes
- Search fallback chain:
  1. Ollama `web_search`
  2. Serper API (if `SERPER_API_KEY` is set)
  3. DuckDuckGo HTML scraping fallback
- Content fetch fallback:
  1. Ollama `web_fetch`
  2. Trafilatura extraction
- Context validation before prompt injection
- Debug logs for pipeline observability
- Ollama readiness check before each turn

## Project Structure

```text
.
├── ollama_web_search.py     # Main pipeline + CLI
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── pyrightconfig.json       # Type-checker config
└── sys_msg.py               # Legacy prompt module (currently unused)
```

## Requirements

- Python 3.10+
- Ollama installed and running
- Ollama Python SDK `>=0.6.0`
- Internet access for search-enabled turns
- Optional: Serper API key for better search quality

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Start Ollama:

```bash
ollama serve
```

Pull your preferred model (example):

```bash
ollama pull granite4:latest
```

## Environment Variables

Set these in `.env`:

- `OLLAMA_MODEL` (default in code: `qwen2.5:0.5b`)
- `OLLAMA_HOST` (example: `http://localhost:11434`)
- `OLLAMA_API_KEY` (optional, for secured remote Ollama hosts)
- `SERPER_API_KEY` (optional)
- `AGENT_DEBUG` (`1` or `0`)

## Usage

Interactive chat:

```bash
python ollama_web_search.py
```

One-shot query:

```bash
python ollama_web_search.py "latest bitcoin price in USD"
```

With options:

```bash
python ollama_web_search.py --model granite4:latest --max-results 5 --debug "your query"
```

## Pipeline Overview

1. `search_or_not_agent()` decides if fresh data is needed.
2. `query_generator_agent()` generates a concise search query.
3. `search_engine_results_scraper()` tries:
   1. Ollama `web_search`
   2. `_serper_search()`
   3. `_duckduckgo_search()`
4. `best_search_result_agent()` picks the best URL.
5. `best_result_scraper()` fetches content (`web_fetch` then Trafilatura).
6. `data_validation_agent()` validates context relevance.
7. Context is appended to user payload only when validated.
8. `stream_assistant_response()` streams final output.

## System Design UML

```mermaid
flowchart TD
    U[User CLI] --> M[Main]
    M --> RT[Run Turn]
    RT --> OR{Ollama Ready}
    OR -- No --> E1[Print Unreachable Error]
    OR -- Yes --> SN[Search Or Not Agent]
    SN --> SD{Search Needed}
    SD -- No --> SA[Stream Assistant Response]
    SD -- Yes --> QG[Query Generator Agent]
    QG --> SE[Search Engine Results Scraper]

    SE --> T1{Tier One}
    T1 --> OWS[Ollama Web Search]
    OWS -->|No Results Or Fail| T2{Tier Two}
    T2 --> SP[Serper API]
    SP -->|No Results Or Fail| T3{Tier Three}
    T3 --> DDG[DuckDuckGo HTML]

    OWS --> BR[Best Search Result Agent]
    SP --> BR
    DDG --> BR

    BR --> BS[Best Result Scraper]
    BS --> WF[Ollama Web Fetch]
    WF -->|Empty Or Fail| TF[Trafilatura Fallback]
    WF --> DV[Data Validation Agent]
    TF --> DV

    DV --> VC{Context Valid}
    VC -- Yes --> AC[Add Context To User Prompt]
    VC -- No --> NP[Use Raw User Prompt]
    AC --> SA
    NP --> SA
    SA --> R[Assistant Response Streamed]
```

## Troubleshooting

- `Ollama is not running or unreachable`
  - Run `ollama serve`.
  - Check `OLLAMA_HOST`.

- `Failed to connect` with `localhost`
  - Use `OLLAMA_HOST=http://127.0.0.1:11434` if your environment resolves `localhost` incorrectly.

- Search quality is weak
  - Set `SERPER_API_KEY` in `.env`.
  - Keep `AGENT_DEBUG=1` to inspect each stage.
