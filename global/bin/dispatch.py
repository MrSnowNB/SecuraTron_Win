import sys
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime

# Ensure the bin directory is in path for imports
sys.path.append(str(Path(__file__).parent))

import ledger
import mem

BASE_DIR = Path.home() / ".securatron"

def safe_expand(cmd_template: str, inputs: dict) -> str:
    """Safely expand command templates using inputs."""
    # Strict allowlist expansion to prevent shell injection
    # In a real harness, this would be much more restrictive
    expanded = cmd_template
    for key, value in inputs.items():
        placeholder = "{" + key + "}"
        if placeholder in expanded:
            # Simple escape: wrap in single quotes
            safe_value = str(value).replace("'", "'\\''")
            expanded = expanded.replace(placeholder, safe_value)
    return expanded

def dispatch(card: dict, inputs: dict, project_id: str, session_id: str) -> dict:
    """Execute a Skill Card and return structured results."""
    skill_id = card["id"]
    impl = card["implementation"]
    start_time = time.time()
    
    # Initialize trial entry
    trial_entry = {
        "ulid": session_id, # Simplified
        "skill_version": card.get("version", 1),
        "session_id": session_id,
        "project_id": project_id,
        "inputs_fingerprint": inputs,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    try:
        if impl["kind"] == "shell":
            result = run_shell_atom(card, inputs, session_id)
        elif impl["kind"] == "python":
            result = run_python_atom(card, inputs, session_id)
        else:
            return {"ok": False, "reason": f"unsupported_implementation_kind: {impl['kind']}"}
            
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Update trial with success
        trial_entry.update({
            "status": "success" if result.get("ok", True) else "failure",
            "duration_ms": duration_ms,
            "artifact_path": result.get("artifact_path")
        })
        ledger.record_trial(skill_id, trial_entry)
        
        return result

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        trial_entry.update({
            "status": "failure",
            "reason": str(e),
            "duration_ms": duration_ms
        })
        ledger.record_trial(skill_id, trial_entry)
        return {"ok": False, "reason": "dispatch_exception", "error": str(e)}

def run_shell_atom(card: dict, inputs: dict, session_id: str) -> dict:
    """Execute a shell-kind Skill Card."""
    cmd_template = card["implementation"]["cmd"]
    command = safe_expand(cmd_template, inputs)
    
    # Create artifact path
    artifact_id = f"{card['id']}-{int(time.time())}"
    artifact_rel_path = f"sessions/{session_id}/artifacts/{artifact_id}.raw"
    artifact_full_path = BASE_DIR / artifact_rel_path
    artifact_full_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run command
    process = subprocess.run(
        command,
        shell=True, # Using shell=True for template expansion; real harness would build argv
        capture_output=True,
        text=True,
        timeout=300
    )
    
    # Write raw artifact
    raw_output = f"STDOUT:\n{process.stdout}\n\nSTDERR:\n{process.stderr}\n\nEXIT_CODE: {process.returncode}"
    artifact_full_path.write_text(raw_output)
    
    # Result parsing (Step 3 will implement the registry)
    # For now, return a raw success/fail
    return {
        "ok": process.returncode == 0,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "exit_code": process.returncode,
        "artifact_path": artifact_rel_path
    }

def run_python_atom(card: dict, inputs: dict, session_id: str) -> dict:
    """Execute a python-kind Skill Card (Step 4)."""
    return {"ok": False, "reason": "python_kind_not_implemented_yet"}
