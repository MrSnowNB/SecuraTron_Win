import json
import hashlib
from pathlib import Path
from datetime import datetime
from ulid import ULID

BASE_DIR = Path.home() / ".securatron"
LEDGER_DIR = BASE_DIR / "global" / "ledger"

def inputs_hash(inputs: dict) -> str:
    """Generate a stable SHA-256 hash of the inputs for distinct input counting."""
    canonical_json = json.dumps(inputs, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_json).hexdigest()}"

def record_trial(skill_id: str, entry: dict):
    """Append a trial entry to the skill-specific ledger."""
    ledger_file = LEDGER_DIR / f"{skill_id}.trials.jsonl"
    
    # Enforce canonical schema
    canonical = {
        "trial_id":           entry.get("trial_id") or 
                              entry.get("ulid") or 
                              str(ULID()),
        "ts":                 entry.get("ts") or 
                              entry.get("timestamp") or 
                              datetime.utcnow().isoformat() + "Z",
        "skill_id":           skill_id,
        "target":             entry.get("target") or
                              (entry.get("inputs_fingerprint") or {})
                              .get("target", "unknown"),
        "result":             entry.get("result") or 
                              entry.get("status") or 
                              "unknown",
        "inputs_hash":        entry.get("inputs_hash") or (
                              inputs_hash(entry["inputs_fingerprint"])
                              if "inputs_fingerprint" in entry else None),
        "inputs_fingerprint": entry.get("inputs_fingerprint", {}),
    }
    # Preserve any extra fields caller provided
    for k, v in entry.items():
        if k not in canonical:
            canonical[k] = v
            
    with open(ledger_file, "a") as f:
        f.write(json.dumps(canonical) + "\n")

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
                # Support both old "status" and new "result" fields
                if entry.get("result") == "success" or entry.get("status") == "success":
                    summary["success"] += 1
                else:
                    summary["failure"] += 1
                
                if "inputs_hash" in entry:
                    summary["distinct_inputs"].add(entry["inputs_hash"])
                
                # Support both old "timestamp" and new "ts" fields
                summary["last_run"] = entry.get("ts") or entry.get("timestamp")
            except json.JSONDecodeError:
                continue
                
    return {
        "success": summary["success"],
        "failure": summary["failure"],
        "distinct_inputs": len(summary["distinct_inputs"]),
        "last_run": summary["last_run"]
    }
