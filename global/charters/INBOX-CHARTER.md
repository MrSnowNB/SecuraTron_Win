---
document_type: charter
document_id: securatron.stagecraft.inbox
version: 0.1
status: living
authority: binding
precedence_above: []
precedence_below:
  - hermes.soul
  - securatron.charters.MEMORY-CHARTER
target_audience: ai_agent
agent_compatibility:
  - claude_code
  - gemini_cli
  - hermes_local
  - codex
adherence: mandatory
read_before:
  - any_stagecraft_inbox_modification
  - any_watcher_or_dispatcher_authorship
  - any_molecule_destructive_action
created: 2026-04-27
last_revised: 2026-04-27
revision_policy: append_only
stop_conditions:
  - charter_incomplete
  - charter_contradicts_itself
  - work_does_not_map_to_section
  - hard_rule_violation_required
forbidden_dependencies:
  - cloud_api
  - orm_framework
  - migration_tooling
canonical_paths:
  charter: ~/.securatron/global/charters/INBOX-CHARTER.md
  mesh_transport: ~/.securatron/global/charters/MESH-TRANSPORT-CHARTER.md
  ticket_schema: ~/.securatron/global/charters/inbox-ticket.schema.json
  inbox_root: ~/.securatron/projects/lab-internal/inbox/
  watcher: ~/.securatron/global/bin/inbox_watcher.py
  dispatcher: ~/.securatron/global/bin/dispatch.py
  ledger: ~/.securatron/global/ledger/*.jsonl
hard_rules_section: III
directory_architecture_section: IV
ticket_schema_section: V
watcher_contract_section: VI
fulfillment_criteria_section: VII
forbidden_actions_section: VIII
revision_proposal_section: IX
provenance:
  - maildir_three_directory_atomicity
  - lpd_print_spooler_queues
  - soar_playbook_human_gates
  - salesforce_file_drop
  - jenkins_fstrigger
  - mwp_folder_orchestration
---

# The SecuraTron Inbox Charter (Stagecraft)

> **Status:** Living document. Append-only revisions. Last manifested: 2026-04-27
> **Authority:** This Charter is binding for any agent constructing or modifying
> the SecuraTron inbox subsystem. It supersedes ad-hoc instruction.
> **Precedence:** `HERMES.md` governs identity. This Charter governs the inbox
> transport layer. MEMORY-CHARTER.md governs the memory organ. Where they appear
> to conflict, `HERMES.md` wins and this Charter is revised, never the reverse.
> **Scope:** This Charter covers the inbox ticket lifecycle, the Maildir three-directory
> discipline, the inotify watcher, the ticket schema, and the dispatch contract.
> It does NOT cover mesh transport (LoRa/Meshtastic) — that is the MESH-TRANSPORT-CHARTER.

---

## I. Adherence Directive — Read Before Every Inbox Task

You are constructing the SecuraTron inbox (Stagecraft) subsystem. This is not an
optimization, a feature, or a convenience. It is the transport substrate that makes
ticket-in/ticket-out work deterministic across agents, sessions, and future mesh
transport layers. Without it, every new molecule rediscovers the same races. With
it, knowledge compounds and multi-agent workflows become reliable.

**You will adhere to this Charter.** You will not invent new directories. You will
not bypass the tmp/new/cur atomicity. You will not consume from tmp/. You will not
improvise the ticket schema.

If this Charter is incomplete or contradictory, you will **STOP** and write a
Revision Proposal appended to Section IX. You will not proceed under uncertainty.

If at any point you find yourself drafting code that does not map to a section of
this Charter, **STOP**. Either the work is out of scope or the Charter is
incomplete. Both require pause, not proceed.

The signal of correct adherence is that your commit messages and your
post-mortem reference Charter section numbers verbatim. The signal of failed
adherence is silent improvisation.

---

## II. Identity of the Inbox System

The inbox is a folder-based orchestration substrate. It implements a
producer/consumer pattern with explicit directory gates. The system has four
layers. Each layer has a single responsibility. Layers do not share responsibilities.

### Layer 0 — Producer Publish

The producer (agent, script, or external system) writes a ticket JSON file into
`tmp/` then performs a single `mv` call to `new/`. The `mv` is atomic on the same
filesystem. This is the publish boundary. Nothing consumes from `tmp/`.

### Layer 1 — Inbox Watcher

The watcher monitors `new/` using `os.inotify` (on Linux) and picks up new
tickets as they appear. It validates the ticket schema, resolves the target
molecule, and dispatches the ticket. On success, it moves the ticket file to
`cur/`. On schema/validation failure, it moves the ticket to `quarantine/`.

### Layer 2 — Molecule Dispatch

The molecule receives the ticket via `dispatch.py`, executes the work, and writes
the result to the ledger (`global/ledger/*.jsonl`). The molecule is transport-agnostic
— it receives a ticket dict and returns a result dict. It does not know whether the
ticket came from a file drop, a future mesh transport, or a direct API call.

### Layer 3 — Ledger Record

The result is appended to the cold canonical ledger. The inbox ticket file is now
redundant (the ledger is the source of truth). The ticket sits in `cur/` until the
operator clears it. This is a delivery artifact, not a storage medium.

> **The inbox is delivery. The ledger is truth. This is non-negotiable.**

### Named Queues

Following the LPD precedent, the inbox supports named sub-queues. Each queue
has its own `tmp/`, `new/`, `cur/`, and `quarantine/` directories. The watcher
monitors each queue independently with configurable behavior.

Default queues at creation:
- `inbox/` — general purpose
- `inbox.urgent/` — high-priority, immediate dispatch
- `inbox.batch/` — low-priority, batch processing

Additional queues are created per operator request via Revision Proposal.

---

## III. Hard Rules

- **HR-INBOX-1 — Maildir Atomicity.** Producers MUST write to `tmp/{ticket_id}.json`
  then atomically `mv` to `new/`. Watchers MUST NOT consume from `tmp/`. The
  `mv` syscall is the publish boundary. Partial writes in `new/` are impossible
  because the file does not exist until the `mv` completes. This rule is inherited
  from the Maildir (1996) lineage. Violation risk: a producer crashes mid-write,
  leaving a half-written file in `new/`. The watcher must reject partial JSON, not
  attempt to parse it.

- **HR-INBOX-2 — Named Queues, Per-Queue Policy.** Each queue is a separate
  directory tree (`tmp/`, `new/`, `cur/`, `quarantine/`). Each queue has an
  independent watcher with configurable behavior (priority, throttle, human-gate).
  Queues MUST NOT be multiplexed. A destructive-queue watcher MUST NOT process
  tickets from a non-destructive queue. This rule is inherited from the LPD
  print spooler (1959) lineage. Violation risk: a batch-queue watcher stalls the
  urgent queue.

- **HR-INBOX-3 — Destructive Actions Require Human Gate.** Any molecule that
  performs destructive or privileged actions (data deletion, config modification,
  network disruption, privilege escalation) MUST include an explicit `human_gate`
  step in its dispatch flow. The step halts execution and waits for operator
  approval before proceeding. The default is `operator-out-of-the-loop = wrong`.
  This rule is inherited from SOAR playbook (2010s) lineage. Violation risk: an
  automated molecule executes destructive actions without human awareness.

- **HR-INBOX-4 — Filename Matching + Age-Threshold Pickup.** The watcher picks up
  tickets whose filenames match the queue's pattern (default: `*.json`). Tickets
  older than a configurable age threshold (default: 24 hours) in `new/` WITHOUT
  being consumed are retried once. This rule is inherited from the Salesforce File
  Drop lineage. Violation risk: a stuck ticket silently ages in `new/` and the
  operator never notices. The age-threshold retry is the safety net.

- **HR-INBOX-5 — inotify Preferred, Polling Fallback Configurable.** On Linux,
  the watcher MUST use `os.inotify` (push-based, zero CPU overhead, sub-millisecond
  latency). Polling (e.g., `time.sleep(N)`) is permitted only as a fallback when
  inotify is unavailable (e.g., container environments without inotify support).
  The polling interval must be configurable. This rule is inherited from the
  Jenkins fstrigger lineage. Violation risk: polling wastes CPU cycles and has
  inherent latency. inotify is strictly superior on Linux.

- **HR-INBOX-6 — Ticket Schema Is a Versioned File in Code, Never Implicit.** The
  ticket schema MUST be authored as a versioned JSON Schema file at
  `global/charters/inbox-ticket.schema.json`. Watcher validation uses this file,
  not hardcoded field lists. Schema changes require a Charter revision (Section IX).
  This rule prevents schema drift between the charter and the implementation.
  Inherited from the MWP (arXiv 2603.16021, 2026) academic lineage on folder-as-orchestration
  substrate. Violation risk: schema evolves in code without documentation, causing
  silent mismatches between producers and watchers.

- **HR-INBOX-7 — Inbox-as-Delivery, Ledger-as-Truth.** Inbox files (`new/`,
  `cur/`) are transient delivery mechanisms. The ledger (`global/ledger/*.jsonl`)
  is the authoritative record of all ticket outcomes. Inbox files are never the
  source of truth. They are never deleted from `new/` or `cur/` — they are moved
  to `cur/` on dispatch and persist there until explicit operator removal.
  Quarantine files persist until explicit operator removal. This rule is
  SecuraTron-native, proposed by Hermes. Violation risk: treating inbox files
  as durable storage leads to data loss on cleanup and breaks the ledger-as-truth
  principle.

---

## IV. Directory Architecture

The inbox root lives at `~/.securatron/projects/lab-internal/inbox/`. Each queue
is a sub-directory with four mandatory sub-directories.

```
inbox/
├── tmp/            # Producer write target (not watched)
├── new/            # Published tickets (watched by inotify)
├── cur/            # Completed/dispatched tickets (not watched)
└── quarantine/     # Failed tickets (not watched, operator-managed)

inbox.urgent/
├── tmp/
├── new/
├── cur/
└── quarantine/

inbox.batch/
├── tmp/
├── new/
├── cur/
└── quarantine/
```

### Publish Protocol (Producer)

1. Producer creates ticket JSON in `tmp/{ticket_id}.json`
2. Producer writes the COMPLETE file to disk
3. Producer calls `mv tmp/{ticket_id}.json new/{ticket_id}.json`
4. The `mv` is the publish event. The watcher picks it up.

### Pickup Protocol (Watcher)

1. Watcher detects `IN_MOVED_TO` event for `new/{ticket_id}.json`
2. Watcher reads and validates the ticket against the JSON Schema
3. If valid: watcher dispatches the ticket to the appropriate molecule
4. If invalid: watcher moves the ticket to `quarantine/{ticket_id}.json`
5. On successful dispatch: watcher moves the ticket to `cur/{ticket_id}.json`

### Cleanup Protocol (Operator)

1. Operator manually removes files from `cur/` and `quarantine/`
2. No automated cleanup. These directories are append-only.
3. The ledger is the authoritative record — inbox cleanup is cosmetic.

---

## V. Ticket Schema (Authoritative)

The ticket schema is versioned and lives at
`~/.securatron/global/charters/inbox-ticket.schema.json`. The schema file is
referenced here at v1.0. Any changes to the schema require a Charter revision.

### v1.0 Schema (Draft)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "securatron/inbox-ticket/1.0",
  "title": "SecuraTron Inbox Ticket",
  "description": "A ticket submitted to the Stagecraft inbox for dispatch.",
  "type": "object",
  "required": [
    "ticket_id",
    "source",
    "skill",
    "priority",
    "created_at",
    "status"
  ],
  "properties": {
    "ticket_id": {
      "type": "string",
      "pattern": "^TICK-[A-F0-9]{8}$",
      "description": "Unique ticket identifier. Format: TICK-<8 hex chars>."
    },
    "source": {
      "type": "string",
      "enum": ["agent", "operator", "mesh", "external", "cron"],
      "description": "Origin of the ticket."
    },
    "skill": {
      "type": "string",
      "description": "Skill ID to dispatch to (e.g., 'web.nikto', 'recon.gobuster')."
    },
    "target": {
      "type": "string",
      "description": "Target for the skill (e.g., 'scanme.nmap.org')."
    },
    "inputs": {
      "type": "object",
      "description": "Skill-specific input parameters.",
      "additionalProperties": true
    },
    "priority": {
      "type": "string",
      "enum": ["low", "normal", "high", "urgent"],
      "default": "normal"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp of ticket creation."
    },
    "status": {
      "type": "string",
      "enum": ["pending", "processing", "completed", "failed", "quarantined"],
      "default": "pending"
    },
    "human_gate": {
      "type": "boolean",
      "default": false,
      "description": "If true, the dispatch must halt for operator approval before proceeding."
    },
    "destructive": {
      "type": "boolean",
      "default": false,
      "description": "If true, the ticket contains destructive or privileged actions. Implies human_gate=true."
    },
    "result": {
      "type": "object",
      "description": "Filled in by the molecule after dispatch. Not required at submission.",
      "properties": {
        "ok": {"type": "boolean"},
        "result": {"type": "string"},
        "output": {"type": "string"}
      }
    },
    "ledger_offset": {
      "type": "integer",
      "description": "Byte offset in the source JSONL where the result was written. Filled by watcher on dispatch."
    }
  }
}
```

### Field Semantics

| Field | Required | Description |
|-------|----------|-------------|
| `ticket_id` | Yes | Unique identifier. Producer responsibility. |
| `source` | Yes | Origin: agent, operator, mesh, external, cron. |
| `skill` | Yes | Skill ID. Maps to a molecule in `dispatch.py`. |
| `target` | No | Target for the skill. |
| `inputs` | No | Skill-specific input parameters (arbitrary object). |
| `priority` | Yes | Low, normal, high, urgent. Determines queue routing. |
| `created_at` | Yes | ISO 8601 timestamp. |
| `status` | Yes | Pending → Processing → Completed/Failed/Quarantined. |
| `human_gate` | No | Defaults to false. If true, operator approval required. |
| `destructive` | No | Defaults to false. If true, implies human_gate=true. |
| `result` | No | Filled by molecule. Not required at submission. |
| `ledger_offset` | No | Filled by watcher on dispatch. |

---

## VI. Watcher Contract

The watcher is a long-running Python process at
`~/.securatron/global/bin/inbox_watcher.py`. It is the heartbeat of the inbox
subsystem.

### Responsibilities

1. **Monitor queues.** Watch all configured queue directories (`new/`) using
   `os.inotify`. Default: `inbox/new/`, `inbox.urgent/new/`, `inbox.batch/new/`.
2. **Pick up tickets.** On `IN_MOVED_TO` event, read the file, validate against
   the JSON Schema (Section V), and dispatch or quarantine.
3. **Dispatch.** Call `dispatch.py` with the appropriate skill and inputs.
4. **Track status.** Update ticket `status` field and `ledger_offset` on dispatch.
5. **Move files.** On success: move to `cur/`. On failure: move to `quarantine/`.
6. **Age-threshold retry.** If a ticket has been in `new/` longer than the
   configurable age threshold (default: 24h) without being consumed, retry once.

### Configuration

Configuration is in `config.yaml` under `stagecraft.inbox`:

```yaml
stagecraft:
  inbox:
    root: ~/.securatron/projects/lab-internal/inbox/
    queues:
      - name: inbox
        path: inbox
        priority: normal
      - name: inbox.urgent
        path: inbox.urgent
        priority: urgent
      - name: inbox.batch
        path: inbox.batch
        priority: low
    transport:
      backend: inotify         # inotify | poll
      poll_interval: 5         # seconds (only used if backend=poll)
    age_threshold: 86400       # seconds (24h)
    max_retries: 1
    schema_path: ~/.securatron/global/charters/inbox-ticket.schema.json
```

### Error Handling

- Schema validation failure: ticket → `quarantine/`. Log reason. Do not crash.
- Missing skill: ticket → `quarantine/`. Log reason. Do not crash.
- Dispatch failure: ticket → `quarantine/`. Log reason. Do not crash.
- Watcher crash: on restart, rescan `new/` for unconsumed tickets. Apply age-threshold logic.

### Signal Handling

The watcher MUST handle `SIGTERM` and `SIGINT` gracefully:
- Stop accepting new events
- Complete in-progress dispatch
- Exit cleanly

---

## VII. Acceptance Criteria — Charter Fulfillment

The Inbox Charter is fulfilled when ALL of the following are true:

- [ ] `global/charters/INBOX-CHARTER.md` exists with all Sections I through X
- [ ] `global/charters/inbox-ticket.schema.json` exists and validates the v1.0 schema
- [ ] `projects/lab-internal/inbox/` directory tree created with `tmp/`, `new/`, `cur/`, `quarantine/` for default queues (`inbox/`, `inbox.urgent/`, `inbox.batch/`)
- [ ] `global/bin/inbox_watcher.py` exists and uses `os.inotify` (not polling) for the default backend
- [ ] The watcher validates incoming tickets against the JSON Schema from Section V
- [ ] On valid ticket: watcher dispatches via `dispatch.py` and moves ticket to `cur/`
- [ ] On invalid ticket: watcher moves ticket to `quarantine/` and logs reason
- [ ] The watcher handles `SIGTERM`/`SIGINT` gracefully (no orphaned processes)
- [ ] `projects/lab-internal/scope.yaml` includes `stagecraft.inbox` as an active scope
- [ ] `dispatch.py` can dispatch at least one sample ticket end-to-end (produce → watch → dispatch → ledger)
- [ ] A post-mortem is written to `global/post-mortems/inbox-charter-fulfillment.md` capturing what was difficult, what was unexpected, and what should change in v2 of this Charter

If any criterion fails, the Charter is not fulfilled. The work is not complete.
**There is no partial credit.**

---

## VIII. Forbidden Actions

The following actions are explicitly forbidden under this Charter. Performing
any of them invalidates the build regardless of Section VII.

- Writing to `tmp/` and having a watcher consume from `tmp/` (violates HR-INBOX-1)
- Consuming partially-written files (the `mv` from `tmp/` is the publish boundary)
- Multiplexing incompatible queues (violates HR-INBOX-2)
- Auto-executing destructive molecules without human_gate (violates HR-INBOX-3)
- Hardcoding the ticket schema in watcher code instead of using the JSON Schema file (violates HR-INBOX-6)
- Treating inbox files as durable storage (violates HR-INBOX-7)
- Automated cleanup of `new/` or `cur/` (these are append-only)
- Using polling as the default backend on Linux (violates HR-INBOX-5)
- Deleting quarantine files without operator action (quarantine is operator-managed)
- Adding mesh transport logic to this Charter (that is the MESH-TRANSPORT-CHARTER scope)

---

## IX. Revision Proposals (Append-Only)

### RP-INBOX-001: Molecule-to-skill mapping convention
**Proposed by:** hermes (uncertainty)
**Date:** 2026-04-27
**Section affected:** II, VI
**Problem:** This Charter defines the ticket schema and the watcher but does not
specify how `skill` values in tickets map to concrete molecule implementations.
The mapping `web.nikto → molecules/web/nikto.py` is a reasonable default, but
it is not formalized here.
**Proposed change:** Add a subsection in Section VI defining the skill-to-molecule
path convention (e.g., `skill_id` is a dotted path resolving to `molecules/{skill_id}.py`).
**Justification:** Without a mapping convention, `dispatch.py` cannot route tickets
to molecules deterministically.
**Status:** pending — operator to accept or revise

### RP-INBOX-002: Ticket auth primitive (CA96)
**Proposed by:** hermes (deferred)
**Date:** 2026-04-27
**Section affected:** V
**Problem:** The ticket schema has no authentication field. Future mesh transport
(Lora/Meshtastic) and external sources will need ticket integrity verification.
CA96 research is identified as the eventual primitive but is not ready for v0.1.
**Proposed change:** Add `auth` field to ticket schema (deferred to v0.2). Reserve
the field position. Schema v1.0 leaves `auth` as optional.
**Justification:** Reserving the field avoids a breaking schema change later.
**Status:** deferred — implement when CA96 research matures

### RP-INBOX-003: Batch mode for inbox.batch queue
**Proposed by:** hermes (uncertainty)
**Date:** 2026-04-27
**Section affected:** VI
**Problem:** The `inbox.batch/` queue is defined in Section II but its dispatch
behavior (immediate vs batched) is not specified. Should batch tickets be dispatched
immediately or collected and dispatched in groups?
**Proposed change:** Add configurable batch mode to watcher config. Batch mode
collects tickets for N seconds before dispatching as a group.
**Justification:** Batch processing is the raison d'etre of the batch queue.
Immediate dispatch negates its purpose.
**Status:** pending — operator to accept or revise

### RP-INBOX-004: Mesh transport integration point
**Proposed by:** hermes (deferred)
**Date:** 2026-04-27
**Section affected:** II, V
**Problem:** The `source: "mesh"` value in the ticket schema references the
future MESH-TRANSPORT-CHARTER. The integration point between mesh transport and
the inbox is not defined in this document.
**Proposed change:** Add a subsection in Section II describing the mesh-to-inbox
integration point (mesh writes to inbox/tmp/, inbox watcher picks it up as normal).
**Justification:** Even a placeholder ensures the mesh team knows the inbox schema
is the contract.
**Status:** deferred — implement in parallel with MESH-TRANSPORT-CHARTER draft

---

## X. Charter Provenance

This Charter draws from the Stagecraft research documented in the operator's
provenance record:

- The **Maildir (1996)** three-directory atomicity pattern: `tmp/` for writes,
  `mv` to `new/` for atomic publish. The single `mv` syscall is one of the most
  elegant patterns in computing for exactly this use case. Inherited hard rule:
  write to `tmp/`, `mv` to `new/`. Watchers MUST NOT consume from `tmp/`.

- The **LPD / Print Spooler (1959)** named queue pattern: separate queues with
  per-queue policy. Inherited hard rule: do not multiplex incompatible workloads.
  Each queue gets its own watcher with configurable behavior.

- The **SOAR Playbooks (2010s)** human-in-the-loop gates: destructive actions
  require analyst approval before execution. Inherited hard rule: operator-out-of-the-loop
  is the wrong default. Destructive molecules MUST have an explicit `human_gate` step.

- The **Salesforce File Drop** pattern: filename matching, age-threshold pickup,
  failure quarantine, throttling. Inherited hard rule: implement age-threshold retry
  as a safety net for stuck tickets. Quarantine is for failures that need operator review.

- The **Jenkins fstrigger** pattern: configurable polling with inotify preferred
  on Linux. Inherited hard rule: use `os.inotify` on Linux (push-based, zero CPU,
  sub-millisecond). Polling is a fallback only.

- The **MWP (arXiv 2603.16021, 2026)** academic reference: folder-as-orchestration-layer.
  Provides formal grounding for the entire approach. Inherited hard rule: ticket schema
  is a versioned file, never implicit in code.

- **SecuraTron-native** — Hermes-proposed HR-INBOX-7: inbox-as-delivery, ledger-as-truth.
  Inherited hard rule: inbox files are transient delivery mechanisms. The ledger is the
  authoritative record. Never delete from `new/` or `cur/`. Only operators clear quarantine.

The synthesis is SecuraTron-specific: a folder-based orchestration layer with
Maildir atomicity, SOAR human gates, and inotify watchers, all governed by a
versioned ticket schema. This is the minimum viable Stagecraft v1.0. It is not
the final form.

- v0.2 will add ticket auth (CA96), batch mode, and skill-to-molecule mapping
- v0.3 will add the MESH-TRANSPORT-CHARTER integration
- v1.0 will add SOAR connector with analyst approval workflow
- v2.0 will add the encoding tiers (JSON 200B / CBOR 64B / binary 13B) for mesh transport

None of those happen until v0.1 is fulfilled.

---

## XI. Design Decision Spectrum

The Stagecraft subsystem sits on a design spectrum. Each step adds cost but also
durability and integration:

| Step | Architecture | Cost | Durability | Integration |
|------|-------------|------|------------|-------------|
| 0 | Bash one-liner | Minutes | Throwaway | None |
| 1 | Stagecraft v1.0 (this Charter) | ~1 day | Production-grade | SecuraTron-native |
| 2 | SOAR connector | 3-5 days | Enterprise | Plugs into existing SOAR |

This Charter covers Step 1. Steps 0 and 2 are documented here for context.
Step 0 (bash one-liner) was considered and rejected: it has no atomicity, no
schema validation, no quarantine, and no dispatch contract. Step 2 (SOAR
connector) is viable only after Step 1 is stable — the ticket schema and
dispatch contract defined here are prerequisites for SOAR integration.

---

— End of Charter v0.1 —
