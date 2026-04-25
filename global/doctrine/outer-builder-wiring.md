# Doctrine: Outer Builder Wiring

## Codex CLI (T-CODEX-LEMONADE-WIRING-001)
- **Version:** 0.72.0 (pinned for stability)
- **Status:** Proven wiring, stable tool-calling.

## Hermes Agent (T-HERMES-LEMONADE-WIRING-001)

- **Version installed:** Hermes Agent v0.11.0 (2026.4.23)
- **Config path:** ~/.hermes/config.yaml
- **Base URL:** http://localhost:13305/api/v1
- **Primary model:** Qwen3.6-27B-GGUF
- **Fast model:** Qwen3.6-35B-A3B-GGUF
- **SOUL.md:** Configured to reference Securatron doctrine and observe harness boundaries.
- **Smoke test:** PASS.
- **Tool-call validation:** PASS. Hermes utilizes internal tools to access the filesystem and provides high-quality summaries.
- **Side-by-side comparison vs Codex 0.72:** 
  - **Codex (66s):** Explicitly shows tool invocations (bash, cat) and provides concise, accurate lists.
  - **Hermes (122s):** Slower but more detailed. Summary included risk/side-effect metadata from the Skill Cards that Codex omitted. Output formatting is superior for human reading.
- **Verdict:** Keep. Hermes feels like a more "mature" agent that understands context and doctrine better, while Codex is faster for quick atomic tasks.

## Outer Builder Stack (Current)
- Codex 0.72 + Lemonade + Qwen3.6-27B — proven wire, minimum viable.
- Hermes + Lemonade + Qwen3.6-27B — operational, high-fidelity context awareness.
- Gemini CLI — task-brief driver.
- Both Codex and Hermes are outer builders; neither invokes inner-runtime MCP tools directly.
