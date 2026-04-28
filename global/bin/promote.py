import os
import json
import yaml
import shutil
from pathlib import Path
import sys

# Ensure the bin directory is in path for imports
sys.path.append(str(Path(__file__).parent))

import ledger

BASE_DIR = Path.home() / ".securatron"
INBOX = BASE_DIR / "global" / "inbox"
TOOLS = BASE_DIR / "global" / "tools"

# RP-004: Review prompt must enumerate Section VIII violations.
# This prompt is displayed to the human reviewer when a skill card
# requires human review (requires_human_review == true).
REVIEW_PROMPT = """\
Human Review Required: {atom_id}

Before approving promotion, check for these Section VIII violations:

  [ ] 1. Warm index or *.db files committed to git (HR-8, Section II)
  [ ] 2. Any code path writes to index.db outside reindex.py or the dispatch append-hook (HR-2)
  [ ] 3. Ledger JSONL entries were modified after write (HR-3)
  [ ] 4. Restore gate was bypassed during authorship (HR-4)
  [ ] 5. Cloud or network dependencies introduced in memory path (HR-5)
  [ ] 6. Provenance broken — trial_id or source_path missing (HR-6)
  [ ] 7. ORM frameworks used (SQLAlchemy, Peewee, etc.) instead of direct sqlite3
  [ ] 8. Cold-tier data compressed, pruned, or deleted
  [ ] 9. Warm index treated as durable source of truth
  [ ] 10. pickle or dill used for memory artifacts (security boundary)
  [ ] 11. reindex.py is incremental instead of full rebuild

Additional checks:
  - Skill card schema is complete and matches skill-card.v1.yaml
  - Required success trials met: {required_success}
  - Required distinct inputs met: {required_distinct_inputs}
  - No ad-hoc improvisation outside Charter sections

Recommendation: approve | reject | request_changes
"""

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
    
    # Get runtime behavior from ledger instead of card metadata
    stats = ledger.summarize(card["id"])
    rules = card.get("promotion", {})
    
    # Evaluate against gate rules
    success_met = stats["success"] >= rules.get("required_success", 3)
    distinct_met = stats["distinct_inputs"] >= rules.get("required_distinct_inputs", 3)
    
    if success_met and distinct_met:
        if not rules.get("requires_human_review", False):
            target = TOOLS / f"{card['id']}.yaml"
            with open(target, "w") as f:
                yaml.dump(card, f)
            print(f"PROMOTED: {card['id']} to global tier.")
        else:
            # RP-004: Display review prompt with Section VIII checks
            rules = card.get("promotion", {})
            print(REVIEW_PROMPT.format(
                atom_id=card['id'],
                required_success=rules.get("required_success", 5),
                required_distinct_inputs=rules.get("required_distinct_inputs", 3),
            ))
    else:
        print(f"REJECTED: {card['id']} needs more trials (Success: {stats['success']}/{rules.get('required_success', 3)}, Distinct: {stats['distinct_inputs']}/{rules.get('required_distinct_inputs', 3)}).")

if __name__ == "__main__":
    drain_inbox()
