# Doctrine: Session Lifecycle

## States

### 1. Open
- **Trigger:** `session.open(project_id)`
- **Action:** Create `sessions/<ulid>/` directory. Initialize `plan.json` and `scratchpad.md`.
- **Constraint:** Only one session per project can be active in a single process.

### 2. Active
- **Nature:** Tool-intensive loop.
- **Writes:** Continuous append to `tool_log.jsonl`. Artifact generation in `artifacts/`.

### 3. Closing
- **Trigger:** Model signals task completion.
- **Requirement:** Model must author a `summary.md` and identify potential promotion candidates (new Skill Cards or Decision Logs).

### 4. Closed
- **Action:** Promoter process scans the session.
- **Promotion:** Successful/stable Skill Cards are queued to `global/inbox/`.
- **Cleanup:** Session data is archived or moved to the project's permanent `cases/` folder.

## Session ID
Sessions use **ULIDs** (Universally Unique Lexicographically Sortable Identifier) to ensure chronological sorting and uniqueness across distributed nodes.
