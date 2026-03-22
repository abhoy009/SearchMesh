# Commands

## Environment Requirements
- Python `3.10+`
- Ollama installed and reachable (`ollama serve`)
- Internet access for web-enabled turns
- Optional: Serper API key for stronger search quality

## Install
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Start
```bash
ollama serve
```

## Pull Model (example)
```bash
ollama pull granite4:latest
```

## Run (interactive)
```bash
python ollama_web_search.py
```

Equivalent module entrypoint:
```bash
python -m src.app.cli
```

## Run (one-shot)
```bash
python ollama_web_search.py "latest bitcoin price in USD"
```

## Run (with options)
```bash
python ollama_web_search.py --model granite4:latest --max-results 5 --debug "your query"
```

## Type Check
```bash
pyright
```
- Note: `pyright` must be installed in your environment to run this.

## Test
```bash
python -m unittest discover -s tests -t . -v
```
Current state: basic scaffold tests only.

## Lint
- Lint command: UNKNOWN.

## Format
- Formatter command: UNKNOWN.

## Migrations / Setup Steps
- Database migrations: not applicable in current repo.
