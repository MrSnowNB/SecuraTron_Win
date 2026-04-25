# Doctrine: Tier-Memory Write Rules

## Tier Governance

### 1. Global Tier (`~/.securatron/global/`)
- **Read:** Always.
- **Write:** Restricted to the **Promoter** process.
- **Content:** Validated Skill Cards, shared schemas, core doctrine, and universal semantic context.
- **Strict Rule:** Never written to by tools or models directly.

### 2. Project Tier (`~/.securatron/projects/`)
- **Read:** When project is active.
- **Write:** Restricted to the **Harness Decisions API**.
- **Content:** Scope definitions, decision logs, findings, and playbooks.
- **Mechanism:** The model *proposes* a decision; the harness *commits* it after validation.

### 3. Session Tier (`~/.securatron/sessions/`)
- **Read:** Always.
- **Write:** Free (via Typed API).
- **Content:** Scratchpad, plan, tool logs, and artifacts.
- **Lifecycle:** Exists until session close; data is then analyzed for promotion.

### 4. Stream Tier (Journal)
- **Nature:** Framework-authored and cross-project.
- **Strict Rule:** Append-only. Never patched.

## Attribution Requirement
Every write must include:
- `session_id`
- `project_id`
- `skill_card_id` (if tool-initiated)
- `timestamp`
- `author` (human or model-id)
