import json
import hashlib
from pathlib import Path
from datetime import datetime

BASE_DIR = Path.home() / ".securatron"
LEDGER_DIR = BASE_DIR / "global" / "ledger"

def inputs_hash(inputs: dict) -> str:
    """Generate a stable SHA-256 hash of the inputs for distinct input counting."""
    canonical_json = json.dumps(inputs, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_json).hexdigest()}"

def record_trial(skill_id: str, entry: dict):
    """Append a trial entry to the skill-specific ledger."""
    ledger_file = LEDGER_DIR / f"{skill_id}.trials.jsonl"
    
    # Ensure mandatory fields for consistency
    entry["skill_id"] = skill_id
    if "timestamp" not in entry:
        entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
    if "inputs_hash" not in entry and "inputs_fingerprint" in entry:
        entry["inputs_hash"] = inputs_hash(entry["inputs_fingerprint"])
        
    with open(ledger_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

def summarize(skill_id: str) -> dict:
    """Summarize trial results for a given skill."""
    ledger_file = LEDGER_DIR / f"{skill_id}.trials.jsonl"
    summary = {
        "success": 0,
        "failure": 0,
        "distinct_inputs": set(),
        "last_run": None
    }
    
    if not ledger_file.exists():
        return {
            "success": 0,
            "failure": 0,
            "distinct_inputs": 0,
            "last_run": None
        }
        
    with open(ledger_file, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("status") == "success":
                    summary["success"] += 1
                else:
                    summary["failure"] += 1
                
                if "inputs_hash" in entry:
                    summary["distinct_inputs"].add(entry["inputs_hash"])
                
                summary["last_run"] = entry.get("timestamp")
            except json.JSONDecodeError:
                continue
                
    return {
        "success": summary["success"],
        "failure": summary["failure"],
        "distinct_inputs": len(summary["distinct_inputs"]),
        "last_run": summary["last_run"]
    }
