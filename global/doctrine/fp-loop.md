# Doctrine: First Principles Validation Loop (fp-loop)

## Purpose
Every new atom or molecule runs through this loop before its trial
counts as valid. Prevents fix-forward behavior and ensures failures
are understood, not bypassed.

## Loop Steps

### Step 1 — Decompose
Before running anything, state in writing:
- What is the single observable outcome that proves this worked?
- What inputs are you using and why?
- What would a false positive look like?

### Step 2 — Execute
Run the minimum viable version. Not the full chain — one atom, one
input, confirming the interface works at all.

### Step 3 — Observe
Read actual output. Do not interpret. State exactly:
- What the tool returned (verbatim or summarized faithfully)
- Whether it matches the postconditions defined in the Skill Card

### Step 4 — Gate
Evaluate every postcondition from the Skill Card:
  PASS: postcondition met → log trial as success
  FAIL: any postcondition unmet → log as failure, STOP

Never proceed past a FAIL without operator acknowledgment.
Never treat "it mostly worked" as a pass.

### Step 5 — Adapt (only on failure)
Ask: what assumption was wrong at the first-principles level?
- Wrong input format?
- Wrong scope check?
- Tool not installed?
- Parser schema mismatch?

Identify the minimal change that fixes the root cause.
Make only that change. Re-run from Step 2.

### Step 6 — Promote
After required_success successes across required_distinct_inputs,
the atom is eligible for promotion. Run the promoter:
  python3 ~/.securatron/global/bin/promoter.py --card {skill_id}

Do not promote manually. Let the promoter evaluate the ledger.

## Anti-Patterns (Never Do These)
- Skipping Step 1 (running before defining success)
- Treating a partial result as a pass
- Fixing forward past a postcondition failure
- Promoting an atom based on one input
- Running the full chain before each atom passes alone
