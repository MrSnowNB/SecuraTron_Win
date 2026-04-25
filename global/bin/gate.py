import re
import yaml
from pathlib import Path

BASE_DIR = Path.home() / ".securatron"

def check_scope(card: dict, inputs: dict, project_id: str) -> bool:
    """Validate that inputs (like targets) are within project scope."""
    scope_file = BASE_DIR / "projects" / project_id / "scope.yaml"
    if not scope_file.exists():
        # If no scope is defined, we fail closed for safety
        return False
        
    scope = yaml.safe_load(scope_file.read_text())
    allowed_targets = scope.get("targets", [])
    
    # Check common target fields
    target = inputs.get("target") or inputs.get("host") or inputs.get("url")
    if target and target not in allowed_targets:
        return False
        
    return True

def check_preconditions(card: dict, inputs: dict) -> bool:
    """Evaluate skill card preconditions."""
    preconditions = card.get("preconditions", [])
    if not preconditions:
        return True
        
    # Placeholder for a real expression evaluator
    # For now, we assume simple checks like "fs.exists" are handled by the caller
    return True

def check_secrets(inputs: dict) -> bool:
    """Scan inputs for potential leaks of sensitive data."""
    secret_patterns = [
        r"sk-[a-zA-Z0-9]{32,}", # OpenAI
        r"AIza[0-9A-Za-z-_]{35}", # Google
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----",
    ]
    
    input_str = str(inputs)
    for pattern in secret_patterns:
        if re.search(pattern, input_str):
            return False
    return True

def check_budget(card: dict, session_id: str) -> bool:
    """Check if the tool call fits within the session's resource budget."""
    # Placeholder: would tally tool-log.jsonl entries
    return True

def validate_all(card: dict, inputs: dict, project_id: str, session_id: str) -> tuple[bool, str]:
    """Run all gate checks."""
    if not check_secrets(inputs):
        return False, "secret_leak_detected"
    if not check_scope(card, inputs, project_id):
        return False, "out_of_scope"
    if not check_preconditions(card, inputs):
        return False, "preconditions_not_met"
    if not check_budget(card, session_id):
        return False, "budget_exceeded"
        
    return True, "ok"
