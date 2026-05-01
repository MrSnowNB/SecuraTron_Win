import os
import json
import yaml
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(os.getenv("SECURATRON_HOME", str(Path.home() / ".securatron")))

def read(tier: str, path: str, project_id: str = None, session_id: str = None):
    """Read data from a specific tier."""
    if tier == "global":
        full_path = BASE_DIR / "global" / path
    elif tier == "project" and project_id:
        full_path = BASE_DIR / "projects" / project_id / path
    elif tier == "session" and session_id:
        full_path = BASE_DIR / "sessions" / session_id / path
    else:
        raise ValueError("Invalid tier or missing IDs")
    
    if not full_path.exists():
        return None
        
    if full_path.suffix in [".yaml", ".yml"]:
        return yaml.safe_load(full_path.read_text())
    elif full_path.suffix == ".json":
        return json.loads(full_path.read_text())
    else:
        return full_path.read_text()

def write_session(session_id: str, path: str, data, author: str = "system"):
    """Write data to the session tier."""
    target = BASE_DIR / "sessions" / session_id / path
    target.parent.mkdir(parents=True, exist_ok=True)
    
    metadata = {
        "timestamp": datetime.utcnow().isoformat(),
        "author": author,
        "session_id": session_id
    }
    
    content = {
        "metadata": metadata,
        "payload": data
    }
    
    if path.endswith(".json"):
        target.write_text(json.dumps(content, indent=2))
    elif path.endswith(".jsonl"):
        with open(target, "a") as f:
            f.write(json.dumps(content) + "\n")
    else:
        target.write_text(str(data))

def propose_project(project_id: str, session_id: str, key: str, value: any, author: str):
    """Queue a proposal for the project tier."""
    inbox = BASE_DIR / "global" / "inbox" / f"proj_{project_id}_{datetime.now().timestamp()}.json"
    proposal = {
        "tier": "project",
        "project_id": project_id,
        "session_id": session_id,
        "key": key,
        "value": value,
        "author": author,
        "timestamp": datetime.utcnow().isoformat()
    }
    inbox.write_text(json.dumps(proposal, indent=2))

def propose_global(skill_card: dict, session_id: str, author: str):
    """Queue a proposal for the global tier (Promotion)."""
    inbox = BASE_DIR / "global" / "inbox" / f"glob_{skill_card['id']}_{datetime.now().timestamp()}.json"
    proposal = {
        "tier": "global",
        "session_id": session_id,
        "skill_card": skill_card,
        "author": author,
        "timestamp": datetime.utcnow().isoformat()
    }
    inbox.write_text(json.dumps(proposal, indent=2))
