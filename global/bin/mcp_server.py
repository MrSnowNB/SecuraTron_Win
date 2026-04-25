import sys
import os
from pathlib import Path
import yaml
import json
from fastmcp import FastMCP

# Ensure the bin directory is in path for imports
sys.path.append(str(Path(__file__).parent))

import gate
import mem

mcp = FastMCP("securatron")
TOOLS_DIR = Path.home() / ".securatron/global/tools"

def load_cards():
    """Load all skill cards from the global tools directory."""
    return {c.stem: yaml.safe_load(c.read_text())
            for c in TOOLS_DIR.glob("*.yaml")}

CARDS = load_cards()

@mcp.tool()
def list_skills() -> list[str]:
    """List all registered Skill Cards available as tools."""
    return list(CARDS.keys())

@mcp.tool()
def describe_skill(skill_id: str) -> dict:
    """Return the full Skill Card definition for a given id."""
    if skill_id not in CARDS:
        return {"error": "skill_not_found"}
    return CARDS[skill_id]

@mcp.tool()
def invoke_skill(skill_id: str, inputs: dict, project_id: str, session_id: str) -> dict:
    """Gate and execute a Skill Card. Returns structured result."""
    if skill_id not in CARDS:
        return {"ok": False, "reason": "skill_not_found"}
    
    card = CARDS[skill_id]
    
    # Phase 2d: Pre-tool Gate
    is_valid, reason = gate.validate_all(card, inputs, project_id, session_id)
    if not is_valid:
        # Log failure to session
        mem.write_session(session_id, "tool_log.jsonl", {
            "skill_id": skill_id,
            "inputs": inputs,
            "status": "gate_refused",
            "reason": reason
        })
        return {"ok": False, "reason": f"gate_failed: {reason}"}

    # Phase 3: Actual Dispatch (Stubbed for now)
    result = {
        "ok": False, 
        "reason": "not_implemented", 
        "hint": "Phase 3 will wire up the actual shell/python execution."
    }
    
    # Log attempt to session
    mem.write_session(session_id, "tool_log.jsonl", {
        "skill_id": skill_id,
        "inputs": inputs,
        "status": "not_implemented"
    })
    
    return result

if __name__ == "__main__":
    mcp.run()
