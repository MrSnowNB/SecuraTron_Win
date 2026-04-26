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

## Example 2 — 2026-04-26 12:19 EDT — Promoted Atom With Unverified Scope Gate

**Trigger:** Jules architectural review identified check_preconditions
returns True unconditionally. kali.nmap ran 4 trials with scope
precondition claiming enforcement that never executed.

**Investigation:**
- gate.py check_preconditions was a stub (comment: "Placeholder for 
  a real expression evaluator")
- All 4 kali.nmap promoter trials passed scope check silently
- scanme.nmap.org and 127.0.0.1 are legitimate targets, so no actual
  harm occurred — but the enforcement was theater

**Outcome:**
- Halted molecule build until gate is real
- Implemented scope evaluator with CIDR support and unknown-expression
  hard-fail
- kali.nmap promotion is NOT revoked (targets were legitimate) but
  annotated in ledger

**Lesson:**
A gate that always says PASS is not a gate. 
Unknown precondition expressions must FAIL, not pass silently.
Scope enforcement must be the first thing that actually works,
not the last thing to be implemented.
