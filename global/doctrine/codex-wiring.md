# Doctrine: Codex-Lemonade Wiring (T-CODEX-LEMONADE-WIRING-001-A)

## Configuration Details
- **Codex Version:** 0.72.0 (pinned for tool-call stability)
- **Lemonade Base URL:** `http://localhost:13305/api/v1`
- **Wire API:** `chat` (standard llama.cpp compatibility path)
- **Model Slugs:**
  - `Qwen3.6-27B-GGUF` (Primary)
  - `Qwen3.6-35B-A3B-GGUF` (Profiled)

## Validation Results
- **Step 9 (Smoke Test):** SUCCESS. Model returned `HARNESS_ONLINE`.
- **Step 10 (Tool-Use):** SUCCESS. `Qwen3.6-27B-GGUF` emitted a valid `cat` tool call to read `global/doctrine/memory-rules.md`.
- **Profiles Verified:** `lemonade-27b`.

## Failure Modes Observed
- **Codex 0.125.0:** FAILED. Incompatible with Lemonade's tool schema validation via the `responses` API (Error: `'type' of tool must be 'function'`).
- **Context Limit:** Initial 4096 context was insufficient for Codex overhead; increased global `ctx_size` to 131072.

## Forward Note
If this pairing validates, build a /responses→/chat compatibility shim in Phase 4 to allow migration back to current Codex.
