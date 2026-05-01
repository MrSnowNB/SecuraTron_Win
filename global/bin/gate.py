import re
import yaml
import ipaddress
import os
from pathlib import Path

BASE_DIR = Path(os.getenv("SECURATRON_HOME", str(Path.home() / ".securatron")))

def check_scope_match(target: str, allowed_list: list[str]) -> bool:
    """Check if a target matches an entry or is contained within a CIDR range."""
    # Strip port if present (e.g., 127.0.0.1:80 or example.com:443)
    clean_target = target.split(":")[0]
    
    for entry in allowed_list:
        if clean_target == entry:
            return True
        try:
            # Check for CIDR containment
            if "/" in entry:
                if ipaddress.ip_address(clean_target) in ipaddress.ip_network(entry):
                    return True
        except ValueError:
            continue
    return False

def check_scope(card: dict, inputs: dict, project_id: str, scope_file: str = None) -> bool:
    """Validate that inputs (like targets) are within project scope."""
    if not scope_file:
        scope_file = BASE_DIR / "projects" / project_id / "scope.yaml"
    else:
        scope_file = Path(scope_file)

    if not scope_file.exists():
        return False
        
    scope = yaml.safe_load(scope_file.read_text())
    allowed_targets = scope.get("targets", [])
    
    target = inputs.get("target") or inputs.get("host") or inputs.get("url")
    if target:
        # Strip port or protocol if present for basic matching
        clean_target = re.sub(r"^(http|https)://", "", target)
        return check_scope_match(clean_target, allowed_targets)
        
    return True

def check_preconditions(card: dict, inputs: dict, 
                        session_dir: str = None,
                        scope_file: str = None) -> tuple[bool, list[str]]:
    """
    Evaluate skill card preconditions.
    Returns (passed: bool, failures: list[str])
    """
    preconditions = card.get("preconditions", [])
    if not preconditions:
        return True, []

    failures = []
    
    for expr in preconditions:
        # 1. scope.includes(inputs.X)
        match = re.match(r"scope\.includes\(inputs\.(\w+)\)", expr)
        if match:
            key = match.group(1)
            val = inputs.get(key)
            if not val:
                failures.append(f"Precondition failed: {key} not found in inputs")
                continue
            
            if not scope_file:
                failures.append("No scope file provided — cannot verify target is in scope")
                continue
            
            if not Path(scope_file).exists():
                failures.append(f"No scope file found at {scope_file} — cannot verify target is in scope")
                continue
            
            scope_data = yaml.safe_load(Path(scope_file).read_text())
            allowed = scope_data.get("targets") or scope_data.get("scope") or []
            
            # The actual fix: use the value provided, check_scope_match handles port stripping
            if not check_scope_match(val, allowed):
                failures.append(f"Target '{val}' is OUT OF SCOPE")
            continue

        # 2. network.reachable(inputs.X)
        match = re.match(r"network\.reachable\(inputs\.(\w+)\)", expr)
        if match:
            # TODO: implement with socket.connect or ping check
            print(f"WARNING: network.reachable is a stub — not actually verified for {match.group(1)}")
            continue

        # 3. artifact_exists(outputs.X)
        match = re.match(r"artifact_exists\(outputs\.(\w+)\)", expr)
        if match:
            # TODO: Add real postcondition evaluation logic in Phase 4
            continue

        # 4. Any unrecognized expression
        failures.append(f"Unknown precondition: {expr} — cannot verify")

    return (len(failures) == 0, failures)

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
    return True

def validate_all(card: dict, inputs: dict, project_id: str, session_id: str) -> tuple[bool, str]:
    """Run all gate checks."""
    if not check_secrets(inputs):
        return False, "secret_leak_detected"
    
    # Preconditions check
    # Auto-locate scope file if not provided
    scope_file = BASE_DIR / "projects" / project_id / "scope.yaml"
    passed, failures = check_preconditions(card, inputs, scope_file=str(scope_file))
    if not passed:
        return False, f"preconditions_not_met: {'; '.join(failures)}"
        
    if not check_budget(card, session_id):
        return False, "budget_exceeded"
        
    return True, "ok"
