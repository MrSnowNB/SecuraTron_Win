# Doctrine: Red-Light Examples

This document tracks instances where the Securatron harness or operator intentionally "red-lighted" (halted) an action due to a mismatch between expected and actual system state.

## Example 1 — 2026-04-26 10:15 EDT — Stopped Before False Cleanup

**Trigger:** Gemini CLI diagnostic reported 32 GB total RAM.
User knew physical reality was 128 GB unified on Strix Halo.
Expected ≠ actual. Red-lighted before cleanup.

**Investigation:**
- Cross-checked against Lemonade app telemetry (VRAM 75 GB,
  RAM 28.2 GB in use, 1 model loaded).
- Determined Gemini had read stale `ps` snapshot or cgroup-limited `free`.
- Identified real bug: per-slot `n_ctx_slot = 4096` despite model loaded at 128k.

**Outcome:**
- Did NOT accept Gemini's recommendation to kill three llama-server
  processes and permanently drop context to 16k.
- Applied one-line config fix instead (`-np 1 --ctx-size 131072`).
- Full 128k context preserved; harness capability not degraded.

**Lesson:**
Trust the running server's own telemetry over agent-shell snapshots.
When an agent recommends a capability-reducing fix, check whether the
anomaly driving the recommendation is real or an observer artifact.
