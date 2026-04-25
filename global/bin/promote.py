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
            print(f"PENDING: {card['id']} requires human review.")
    else:
        print(f"REJECTED: {card['id']} needs more trials (Success: {stats['success']}/{rules.get('required_success', 3)}, Distinct: {stats['distinct_inputs']}/{rules.get('required_distinct_inputs', 3)}).")

if __name__ == "__main__":
    drain_inbox()
