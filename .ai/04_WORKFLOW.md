# Workflow

## Branching Approach
- Observed default branch: `main`.
- Branch strategy policy in repo docs: UNKNOWN.

## Development Workflow
1. Create/activate virtual environment.
2. Install dependencies from `requirements.txt`.
3. Configure `.env` from `.env.example`.
4. Start Ollama service.
5. Run CLI in one-shot or interactive mode.
6. Use debug logs (`AGENT_DEBUG=1` or `--debug`) to inspect pipeline behavior.

## Code Review / Handoff
- Formal review process: UNKNOWN.
- Agent handoff convention (now established):
  - Update `.ai/00_CONTEXT.md` and `.ai/08_CHANGELOG.md` after meaningful changes.
  - Update architecture/commands/testing/decisions/open questions when impacted.

## Task Execution Conventions
- Keep prompts deterministic where possible (strict `True/False`, URL-only responses).
- Preserve fallback behavior for degraded network/provider states.
- Do not commit secrets; env values belong in local `.env` only.
