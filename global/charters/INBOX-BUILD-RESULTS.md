# Inbox Build Results — v0.1

**Date:** 2026-04-28
**Builder:** outer-builder
**Subject:** Recursive build validation for Stagecraft Inbox subsystem

## Build Artifacts

| Artifact | Path | Status |
|----------|------|--------|
| Ticket Schema | `global/charters/inbox-ticket.schema.json` | Built, validated |
| Inbox Watcher | `global/bin/inbox_watcher.py` | Built, tested |
| Validation Test Suite | `global/bin/test_inbox_validation.py` | Built, 59/59 passing |
| Inbox Directory Structure | `projects/lab-internal/inbox/` | Created (3 queues) |

## Validation Test Results

### Phase 0 — Schema File Integrity
- **13/13 passed**
- Schema draft 2020-12, `$id: securatron/inbox-ticket/1.0`
- Required fields: ticket_id, source, skill, priority, created_at, status
- additionalProperties=false, allOf constraint (destructive→human_gate)

### Phase 1 — Directory Structure
- **15/15 passed**
- inbox/tmp/, inbox/new/, inbox/cur/, inbox/quarantine/
- inbox.urgent/tmp/, inbox.urgent/new/, inbox.urgent/cur/, inbox.urgent/quarantine/
- inbox.batch/tmp/, inbox.batch/new/, inbox.batch/cur/, inbox.batch/quarantine/

### Phase 2 — Schema Validation
- **9/9 passed**
- Valid ticket passes, missing fields fail, invalid enum values fail
- destructive=true without human_gate=true rejected
- Extra fields rejected (strict mode)

### Phase 3 — Ticket Generation
- **6/6 passed**
- Valid ticket: tmp→new (atomic publish)
- Invalid ticket: written to new/ (not tmp/)
- Destructive+human_gate: valid
- Urgent queue: inbox.urgent/new/

### Phase 4 — Watcher Integration
- **7/7 passed**
- validate_ticket: accepts valid, rejects invalid
- Valid ticket moved to cur/ with status=completed
- Invalid ticket quarantined with reason recorded

### Phase 5 — End-to-End Pipeline
- **9/9 passed**
- Producer: tmp→new publish
- Valid → cur/ completed
- Urgent → inbox.urgent/cur/ completed
- Destructive processed (human_gate)
- Batch ticket processed

### Summary
**59/59 tests passed across 6 phases. 0 failures.**

## Logging Infrastructure

- Phase result JSON files: `~/.securatron/logs/tests/phase-XX_results.json`
- Phase log files: `~/.securatron/logs/tests/phase-XX.log`
- Main watcher log: `~/.securatron/logs/inbox_watcher.log`
- All logs include timestamps, test names, pass/fail status, and details

## Run Command

```bash
python3 ~/.securatron/global/bin/test_inbox_validation.py --all
```

## Revision Proposals

### RP-001: Ticket ID Naming Convention
**Issue:** The schema pattern `^TICK-[A-F0-9]{8}$` is overly restrictive. It only accepts hex digits, which makes natural human-readable IDs impossible (e.g. TICK-VALID01 rejected).  
**Proposal:** Change pattern to `^TICK-[A-Za-z0-9]{8,12}$` to allow alphanumeric IDs up to 12 characters. This maintains uniqueness while enabling human-readable identifiers.  
**Risk:** Low. Existing tests use hex IDs which are still valid under the new pattern.  
**Status:** Open

### RP-002: Test Suite as Cron Job
**Issue:** The validation test suite is a manual command. It should run automatically before any charter or schema changes are committed.  
**Proposal:** Add a cron job that runs `test_inbox_validation.py --all` on every code change to the `global/charters/` or `global/bin/` directories. Fail the build if any test fails.  
**Risk:** Low. Non-intrusive CI pattern.  
**Status:** Open

### RP-003: Ledger Schema Validation
**Issue:** The trial ledger (JSONL) format has no schema definition. The watcher writes to it but there's no validation against a contract.  
**Proposal:** Create `global/charters/ledger-entry.schema.json` for ledger entries. Update the watcher to validate each write.  
**Risk:** Low. Purely additive.  
**Status:** Open

### RP-004: Molecule Dispatch Contract
**Issue:** The watcher's dispatch() method is currently a stub that logs and returns. There's no contract for what a molecule must implement to be dispatchable.  
**Proposal:** Create a molecule contract schema/protocol that defines: required entry points, input validation, output format, and error handling.  
**Risk:** Medium. Changes the dispatcher interface.  
**Status:** Open

### RP-005: inotify Watcher vs Polling
**Issue:** The current watcher uses a hybrid approach — inotify for file detection but still needs a poll loop for new directories. The inotify implementation watches only inbox/new/, not the queue subdirectories themselves.  
**Proposal:** Implement recursive inotify watching on the inbox root so new/ directories are automatically monitored as they are created. This handles the case where new queues are added dynamically.  
**Risk:** Medium. Core infrastructure change.  
**Status:** Open

## Next Steps

1. Address RP-001 (ticket ID naming) — low effort, high usability impact
2. Address RP-004 (molecule dispatch contract) — essential for next build phase
3. Address RP-005 (recursive inotify) — operational improvement
4. Address RP-003 (ledger schema) — needed before production deployment
5. Address RP-002 (cron-based CI) — quality assurance automation

## Gate Status

| Gate | Result |
|------|--------|
| Schema file exists and valid | PASS |
| Directory structure complete (3 queues) | PASS |
| Schema validation (9 tests) | PASS |
| Ticket generation (6 tests) | PASS |
| Watcher integration (7 tests) | PASS |
| End-to-end pipeline (9 tests) | PASS |
| Logging infrastructure | PASS |
| **Overall Build** | **PASS** |
