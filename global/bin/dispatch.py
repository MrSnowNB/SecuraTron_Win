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
import parsers

BASE_DIR = Path.home() / ".securatron"

def safe_expand(cmd_template: str, inputs: dict) -> str:
    """Safely expand command templates using inputs."""
    expanded = cmd_template
    for key, value in inputs.items():
        placeholder = "{" + key + "}"
        if placeholder in expanded:
            safe_value = str(value).replace("'", "'\\''")
            expanded = expanded.replace(placeholder, safe_value)
    return expanded

def dispatch(card: dict, inputs: dict, project_id: str, session_id: str) -> dict:
    """Execute a Skill Card and return structured results."""
    skill_id = card["id"]
    impl = card["implementation"]
    start_time = time.time()
    
    trial_entry = {
        "ulid": session_id,
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
        elif impl["kind"] == "compose":
            result = run_molecule(card, inputs, project_id, session_id)
        else:
            return {"ok": False, "reason": f"unsupported_implementation_kind: {impl['kind']}"}
            
        duration_ms = int((time.time() - start_time) * 1000)
        
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
    # Use inputs for command expansion; don't let card['inputs'] override it
    expand_inputs = dict(inputs)
    # Merge card schema inputs defaults (for keys not in expand_inputs)
    for k, v in card.get("inputs", {}).items():
        if k not in expand_inputs and "default" in v:
            expand_inputs[k] = v["default"]
    command = safe_expand(cmd_template, expand_inputs)
    
    artifact_id = f"{card['id']}-{int(time.time())}"
    artifact_rel_path = f"sessions/{session_id}/artifacts/{artifact_id}.raw"
    artifact_full_path = BASE_DIR / artifact_rel_path
    artifact_full_path.parent.mkdir(parents=True, exist_ok=True)
    
    start_run = time.time()
    process = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=300
    )
    duration_ms = int((time.time() - start_run) * 1000)
    
    raw_output = f"STDOUT:\n{process.stdout}\n\nSTDERR:\n{process.stderr}\n\nEXIT_CODE: {process.returncode}"
    artifact_full_path.write_text(raw_output)
    
    output_type = card["outputs"]["type"]
    parsed = parsers.parse(
        output_type, 
        process.stdout, 
        raw_stderr=process.stderr, 
        exit_code=process.returncode,
        duration_ms=duration_ms,
        inputs=inputs
    )
    
    if not parsed["ok"]:
        return parsed

    return {
        "ok": process.returncode == 0,
        "result": parsed["result"],
        "artifact_path": artifact_rel_path
    }

def run_python_atom(card: dict, inputs: dict, session_id: str) -> dict:
    """Execute a python-kind Skill Card by calling internal modules."""
    method_name = card["implementation"]["method"]
    if method_name == "mem.read":
        from mem import read
        result = read(tier=inputs.get("tier"), path=inputs.get("path"), project_id=inputs.get("project_id"), session_id=inputs.get("session_id") or session_id)
        return {"ok": True, "result": result}
    elif method_name == "mem.write_session":
        from mem import write_session
        write_session(session_id=inputs.get("session_id") or session_id, path=inputs.get("path"), data=inputs.get("data"), author=inputs.get("author", "model"))
        return {"ok": True, "result": {"status": "written"}}
    return {"ok": False, "reason": f"unsupported_python_method: {method_name}"}

def _topo_sort_dag(dag: dict) -> list[str]:
    """
    Return step_ids in valid execution order respecting depends_on.
    Raises ValueError if a cycle is detected or dependency is missing.
    """
    # Build adjacency: step -> set of steps it depends on
    deps = {step_id: set(cfg.get("depends_on", []))
            for step_id, cfg in dag.items()}
    
    # Validate all declared dependencies exist
    for step_id, step_deps in deps.items():
        for d in step_deps:
            if d not in dag:
                raise ValueError(
                    f"Step '{step_id}' depends_on '{d}' "
                    f"which does not exist in DAG"
                )
    
    # Kahn's algorithm
    in_degree = {s: len(d) for s, d in deps.items()}
    queue = [s for s, d in in_degree.items() if d == 0]
    order = []
    
    while queue:
        queue.sort()  # deterministic ordering for equal in-degree
        node = queue.pop(0)
        order.append(node)
        for step_id, step_deps in deps.items():
            if node in step_deps:
                in_degree[step_id] -= 1
                if in_degree[step_id] == 0:
                    queue.append(step_id)
    
    if len(order) != len(dag):
        visited = set(order)
        cycle_nodes = [s for s in dag if s not in visited]
        raise ValueError(f"Cycle detected in DAG involving: {cycle_nodes}")
    
    return order

def run_molecule(card: dict, inputs: dict, project_id: str, session_id: str) -> dict:
    """Execute a molecule by orchestrating its DAG of atoms."""
    dag = card["implementation"]["dag"]
    steps_results = {}
    
    from mcp_server import CARDS
    
    try:
        execution_order = _topo_sort_dag(dag)
    except ValueError as e:
        return {"ok": False, "reason": f"dag_invalid: {e}"}
    
    for step_id in execution_order:
        step_config = dag[step_id]
        atom_id = step_config["atom"]
        if atom_id not in CARDS:
            return {"ok": False, "reason": f"atom_not_found: {atom_id}", "step": step_id}
        
        atom_card = CARDS[atom_id]
        
        resolved_inputs = {}
        for k, v in step_config.get("inputs", {}).items():
            if isinstance(v, str) and "{{" in v and "}}" in v:
                # Handle templates within strings (e.g. host_{{inputs.target}}.json)
                resolved_val = v
                # Resolve inputs.X
                for ink, inv in inputs.items():
                    resolved_val = resolved_val.replace("{{" + f"inputs.{ink}" + "}}", str(inv))
                # Resolve steps.X.result
                for step_name, step_res in steps_results.items():
                    # Handle whole result
                    resolved_val = resolved_val.replace("{{" + f"steps.{step_name}.result" + "}}", json.dumps(step_res.get("result")))
                    # Handle result sub-fields (e.g. steps.scan.result.hosts)
                    if step_res.get("result") and isinstance(step_res["result"], dict):
                        for resk, resv in step_res["result"].items():
                            resolved_val = resolved_val.replace("{{" + f"steps.{step_name}.result.{resk}" + "}}", str(resv))
                resolved_inputs[k] = resolved_val
            else:
                resolved_inputs[k] = v
        
        res = dispatch(atom_card, resolved_inputs, project_id, session_id)
        if not res.get("ok"):
            return {"ok": False, "reason": "step_failed", "step": step_id, "error": res}
        steps_results[step_id] = res
        
    return {
        "ok": True,
        "result": steps_results.get(list(dag.keys())[-1], {}).get("result"),
        "steps": list(steps_results.keys())
    }
