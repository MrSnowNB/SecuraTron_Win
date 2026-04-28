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
            # Simple escape: wrap in single quotes
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
        # Record reason if provided (e.g. timeout)
        if "reason" in result and not result.get("ok"):
             trial_entry["reason"] = result["reason"]

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
    
    # Bug 1 & 2: Fix template variable collision and inject built-ins
    expand_inputs = {}
    
    # 1. Start with card defaults
    for k, v in card.get("inputs", {}).items():
        if isinstance(v, dict) and "default" in v:
            expand_inputs[k] = v["default"]
            
    # 2. Override with trial inputs (source of truth)
    for k, v in inputs.items():
        expand_inputs[k] = v
        
    # 3. Inject automatic built-ins
    expand_inputs['session'] = session_id
    expand_inputs['ts'] = str(int(time.time()))
    
    command = safe_expand(cmd_template, expand_inputs)
    
    # Create artifact path using same logic as command for consistency
    artifact_id = f"{card['id']}-{expand_inputs['ts']}"
    artifact_rel_path = f"sessions/{session_id}/artifacts/{artifact_id}.raw"
    artifact_full_path = BASE_DIR / artifact_rel_path
    artifact_full_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Bug 3: Per-card timeout
    timeout = card.get('execution', {}).get('timeout_seconds', 60)
    
    start_run = time.time()
    try:
        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        duration_ms = int((time.time() - start_run) * 1000)
        
        # Write raw artifact
        raw_output = f"STDOUT:\n{process.stdout}\n\nSTDERR:\n{process.stderr}\n\nEXIT_CODE: {process.returncode}"
        artifact_full_path.write_text(raw_output)
        
        output_type = card["outputs"]["type"]
        parsed = parsers.parse(
            output_type, 
            process.stdout, 
            raw_stderr=process.stderr, 
            exit_code=process.returncode,
            duration_ms=duration_ms,
            inputs=expand_inputs
        )
        
        if not parsed["ok"]:
            return parsed

        return {
            "ok": process.returncode == 0,
            "result": parsed["result"],
            "artifact_path": artifact_rel_path
        }
        
    except subprocess.TimeoutExpired as e:
        duration_ms = int((time.time() - start_run) * 1000)
        # Write what we have so far to artifact if possible (though subprocess usually kills it)
        artifact_full_path.write_text(f"TIMEOUT EXCEEDED ({timeout}s)\nSTDOUT SO FAR:\n{e.stdout}\nSTDERR SO FAR:\n{e.stderr}")
        return {
            "ok": False,
            "reason": "timeout_exceeded",
            "duration_ms": duration_ms,
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
    deps = {step_id: set(cfg.get("depends_on", []))
            for step_id, cfg in dag.items()}
    
    for step_id, step_deps in deps.items():
        for d in step_deps:
            if d not in dag:
                raise ValueError(
                    f"Step '{step_id}' depends_on '{d}' "
                    f"which does not exist in DAG"
                )
    
    in_degree = {s: len(d) for s, d in deps.items()}
    queue = [s for s, d in in_degree.items() if d == 0]
    order = []
    
    while queue:
        queue.sort()
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
                resolved_val = v
                for ink, inv in inputs.items():
                    resolved_val = resolved_val.replace("{{" + f"inputs.{ink}" + "}}", str(inv))
                for step_name, step_res in steps_results.items():
                    resolved_val = resolved_val.replace("{{" + f"steps.{step_name}.result" + "}}", json.dumps(step_res.get("result")))
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

def cli_memory_precheck(args):
    """memory.precheck — Restore Gate (Charter Section V).

    Queries the warm index for prior trial history and related post-mortems,
    then returns a recommendation on whether to proceed with atom authorship.
    """
    import sqlite3
    from datetime import datetime, timedelta
    import re

    skill_id = args.skill
    target = args.target
    limit = args.limit

    # Load post-mortem text for keyword extraction
    pm_dir = BASE_DIR / "global" / "post-mortems"
    pm_texts = {}
    if pm_dir.exists():
        for pm_file in pm_dir.glob("*.md"):
            pm_id = pm_file.stem  # e.g. "web.gobuster"
            pm_texts[pm_id] = pm_file.read_text()

    # Build a set of related atom IDs: any atom sharing the same prefix
    prefix_parts = skill_id.split(".")
    related_atoms = set()
    for pm_id in pm_texts:
        pm_parts = pm_id.split(".")
        # Match if they share the first N-1 parts (same category) or any common atom
        if len(prefix_parts) >= 2 and len(pm_parts) >= 2:
            if prefix_parts[0] == pm_parts[0]:
                related_atoms.add(pm_id)
        if skill_id == pm_id:
            related_atoms.add(pm_id)

    # Load index.db
    db_path = BASE_DIR / "global" / "memory" / "index.db"
    if not db_path.exists():
        return {
            "prior_trials_for_skill": 0,
            "prior_trials_for_target": 0,
            "related_post_mortems": [],
            "known_gotchas_keywords": [],
            "recommendation": "proceed",
            "_warning": "index.db not found — run reindex.py first"
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Prior trials for this skill
    skill_rows = conn.execute(
        "SELECT COUNT(*) as cnt FROM trials WHERE skill_id = ?", (skill_id,)
    ).fetchone()
    prior_skill = skill_rows["cnt"]

    # Prior trials for this target (across all skills)
    target_rows = conn.execute(
        "SELECT COUNT(*) as cnt FROM trials WHERE target = ?", (target,)
    ).fetchone()
    prior_target = target_rows["cnt"]

    # Prior trials for this skill+target combination (for abort detection)
    # RP-003: Abort detection includes timeouts (result IN ('failure','timeout'))
    combo_rows = conn.execute(
        "SELECT COUNT(*) as cnt FROM trials WHERE skill_id = ? AND target = ? AND result IN ('failure','timeout')",
        (skill_id, target)
    ).fetchone()
    recent_failures = combo_rows["cnt"]

    # Related post-mortems (from index, not from pm_texts)
    related_pms = []
    for pm_id in related_atoms:
        row = conn.execute(
            "SELECT atom_id, gotchas, source_path FROM post_mortems WHERE atom_id = ?",
            (pm_id,)
        ).fetchone()
        if row:
            related_pms.append({
                "atom_id": row["atom_id"],
                "gotchas": row["gotchas"],
                "path": row["source_path"]
            })

    # Extract known gotchas keywords from related post-mortems
    gotchas_text = " ".join(pm.get("gotchas", "") or "" for pm in related_pms)
    # Extract keywords: uppercase words, acronyms, technical terms
    raw_keywords = re.findall(r'\b[A-Z]{2,}\b', gotchas_text)
    # Also extract known technical patterns
    tech_patterns = re.findall(r'- \*\*(.*?)\*\*', gotchas_text)
    known_gotchas_keywords = list(dict.fromkeys(raw_keywords + tech_patterns))  # deduplicate, preserve order

    conn.close()

    # Determine recommendation (Charter Section V)
    if recent_failures >= 3:
        recommendation = "abort_pattern_repeat"
    elif related_pms:
        recommendation = "review_attached"
    else:
        recommendation = "proceed"

    return {
        "prior_trials_for_skill": prior_skill,
        "prior_trials_for_target": prior_target,
        "related_post_mortems": related_pms,
        "known_gotchas_keywords": known_gotchas_keywords,
        "recommendation": recommendation
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SecuraTron Dispatcher CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # --- default: dispatch (backward-compatible) ---
    parser_main = subparsers.add_parser("dispatch", help="Run a skill card (backward-compatible)")
    parser_main.add_argument("--skill", required=True, help="Skill ID (e.g., web.gobuster)")
    parser_main.add_argument("--input", action="append", help="Input in key=value format (repeatable)")
    parser_main.add_argument("--project", required=True, help="Project ID")
    parser_main.add_argument("--trials", type=int, default=1, help="Number of trials to run")
    parser_main.add_argument("--session", help="Session ID (optional)")
    parser_main.add_argument("--output-format", choices=["json", "human"], default="human", help="Output format")

    # --- memory.precheck (Charter Section V) ---
    parser_precheck = subparsers.add_parser("memory.precheck", help="Restore gate: check prior trial history and related post-mortems (Charter Section V)")
    parser_precheck.add_argument("--skill", required=True, help="Skill ID being authored (e.g., web.gobuster)")
    parser_precheck.add_argument("--target", required=True, help="Primary target for the skill")
    parser_precheck.add_argument("--limit", type=int, default=10, help="Max results to return")

    args = parser.parse_args()

    # --- Dispatch by subcommand ---
    if args.command == "memory.precheck":
        result = cli_memory_precheck(args)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    elif args.command == "dispatch" or args.command is None:
        # Backward-compatible: dispatch mode (no subcommand or explicit "dispatch")
        inputs = {}
        if args.input:
            for i in args.input:
                if "=" in i:
                    k, v = i.split("=", 1)
                    inputs[k] = v
                else:
                    print(f"Warning: Ignoring malformed input '{i}' (must be key=value)")

        from mcp_server import CARDS
        if args.skill not in CARDS:
            print(f"Error: Skill '{args.skill}' not found")
            sys.exit(1)
        
        card = CARDS[args.skill]
        
        import session as sess_mgr
        session_id = args.session or sess_mgr.open_session(args.project)
        
        results = []
        for t in range(args.trials):
            if args.output_format == "human":
                print(f"--- Trial {t+1}/{args.trials} ---")
            
            result = dispatch(card, inputs, args.project, session_id)
            results.append(result)
            
            if args.output_format == "human":
                print(json.dumps(result, indent=2))
                
        if args.output_format == "json":
            print(json.dumps(results if args.trials > 1 else results[0], indent=2))

    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
