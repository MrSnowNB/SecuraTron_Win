# Skill: Atom Builder

This skill defines the canonical process for building a new SecuraTron Atom from scratch.

## 1. Research & Reference
- Inspect an existing Atom card as a reference (default: `kali.nmap`).
- Verify the tool is installed on the host system.

## 1.5 Memory Pre-check (Charter Section V)
- Use the `memory.precheck` subcommand of `dispatch.py` to identify prior trials or related post-mortems for the target or skill category:
  `python3 global/bin/dispatch.py memory.precheck --skill {skill_id} --target {target}`
- Absorb any "gotchas" or failure patterns from the history before authoring.

## 2. Identification
Identify the following components for the new Atom:
- **Runtime:** `shell` or `python`.
- **Command Template:** The exact command string with `{input}` placeholders.
- **Scope Gate:** The type of scope validation required (e.g., `scope.includes(inputs.target)`).
- **Artifact Format:** The structured output type and path (e.g., `nmap.scan.v1`).

## 3. Authorship
- Write the `card.yaml` and place it in `global/tools/` (draft tier).
- Ensure all mandatory schema fields are present (id, version, implementation, etc.).

## 4. Initial Validation
- Run 1 live trial.
- **Hard Constraint:** Manually verify the `artifact_path` exists on disk before proceeding.

## 5. Hardening
- Run 2 additional trials on distinct targets (e.g., `localhost`, `eth0` IP, or a lab host).
- Confirm that the `inputs_hash` in the ledger correctly differentiates these trials.

## 6. Ledger Audit
- Verify all 3 trials appear in `global/ledger/{atom_id}.trials.jsonl`.
- Ensure each entry follows the canonical schema: `trial_id`, `ts`, `result`, `target`.

## 7. Post-Mortem
- Write a post-mortem document to `global/post-mortems/{atom_id}.md` as per the Hermes doctrine.
- This unblocks the Atom for promotion consideration.
