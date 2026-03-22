# AI Project Memory

Use this folder as the persistent project handoff layer for agents and humans.

## Read Order
1. `00_CONTEXT.md` (quick current-state snapshot)
2. `01_PROJECT.md` (product scope and goals)
3. `02_ARCHITECTURE.md` (code and data flow)
4. `05_COMMANDS.md` and `06_TESTING.md` (how to run/validate)
5. `03_DECISIONS.md`, `04_WORKFLOW.md`, `07_OPEN_QUESTIONS.md`, `08_CHANGELOG.md`

## Update Rules
- Keep files short, factual, and current.
- Never include secrets or private data.
- Use `UNKNOWN` when facts are missing.
- After meaningful changes, update:
  - Always: `00_CONTEXT.md` and `08_CHANGELOG.md`
  - As needed: architecture, decisions, workflow, commands, testing, open questions
- Prefer replacing stale text over appending noise.
