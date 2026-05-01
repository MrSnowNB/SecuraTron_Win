import os
import json
import yaml
import shutil
from pathlib import Path
import sys

# Ensure the bin directory is in path for imports
sys.path.append(str(Path(__file__).parent))

import ledger

BASE_DIR = Path(os.getenv("SECURATRON_HOME", str(Path.home() / ".securatron")))
INBOX = BASE_DIR / "global" / "inbox"
TOOLS = BASE_DIR / "global" / "tools"

REVIEW_PROMPT = """
--- SKILL CARD PROMOTION REVIEW CHECKLIST ---
Verification required for requires_human_review = true.
Please verify that none of the following Section VIII violations have occurred:

1. HR-8: Warm Tier (index.db, pycache, .pyc) committed to version control?
2. HR-2: Direct writes to index.db from outside reindex.py?
3. HR-3: Mutation of cold-tier JSONL entries after write?
4. HR-4: Bypassed memory.precheck during authorship?
5. HR-5: Cloud/Network dependencies added to memory read path?
6. HR-6: Trial results lacking trial_id/source_path provenance?
7. Used ORM frameworks instead of direct sqlite3?
8. Compressed, pruned, or deleted cold-tier data?
9. pickle or dill used for memory artifacts?
10. reindex.py made incremental instead of full rebuild?

Context:
- Skill: {skill_id}
- Successes: {successes}/{req_success}
- Distinct Inputs: {distinct}/{req_distinct}

Approve promotion? (y/N): """

def drain_inbox():
    """Process all proposals in the inbox."""
    for proposal_file in INBOX.glob("*.json"):
        with open(proposal_file, "r") as f:
            proposal = json.load(f)
            
        if proposal["tier"] == "global":
            process_promotion(proposal)
            
        # Archive the processed proposal
        proposal_file.unlink()

def process_promotion(proposal: dict):
    """Evaluate and promote a Skill Card."""
    card = proposal["skill_card"]
    skill_id = card["id"]
    
    # Get runtime behavior from ledger instead of card metadata
    stats = ledger.summarize(skill_id)
    rules = card.get("promotion", {})
    
    # Evaluate against gate rules
    req_success = rules.get("required_success", 3)
    req_distinct = rules.get("required_distinct_inputs", 3)
    
    success_met = stats["success"] >= req_success
    distinct_met = stats["distinct_inputs"] >= req_distinct
    
    if success_met and distinct_met:
        needs_review = rules.get("requires_human_review", False)
        
        if needs_review:
            print(REVIEW_PROMPT.format(
                skill_id=skill_id,
                successes=stats["success"],
                req_success=req_success,
                distinct=stats["distinct_inputs"],
                req_distinct=req_distinct
            ))
            # In a fully autonomous loop, we might wait for operator input.
            # For now, we print and stop as per doctrine.
            print(f"PENDING: {skill_id} requires human review.")
        else:
            target = TOOLS / f"{skill_id}.yaml"
            with open(target, "w") as f:
                yaml.dump(card, f)
            print(f"PROMOTED: {skill_id} to global tier.")
    else:
        print(f"REJECTED: {skill_id} needs more trials (Success: {stats['success']}/{req_success}, Distinct: {stats['distinct_inputs']}/{req_distinct}).")

if __name__ == "__main__":
    drain_inbox()
