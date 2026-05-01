import os
import json
from datetime import datetime
from pathlib import Path
from ulid import ULID

BASE_DIR = Path(os.getenv("SECURATRON_HOME", str(Path.home() / ".securatron")))

def open_session(project_id: str):
    """Open a new session."""
    session_id = str(ULID())
    session_dir = BASE_DIR / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    (session_dir / "scratchpad.md").write_text("# Session Scratchpad\n")
    (session_dir / "plan.json").write_text(json.dumps({"project_id": project_id, "steps": []}))
    (session_dir / "artifacts").mkdir(exist_ok=True)
    
    return session_id

def close_session(session_id: str, summary: str):
    """Close a session and write summary."""
    session_dir = BASE_DIR / "sessions" / session_id
    if not session_dir.exists():
        raise ValueError("Session not found")
        
    (session_dir / "summary.md").write_text(f"# Session Summary\n\n{summary}\n")
    
    # Logic to queue promotion proposals from session history would go here
    print(f"Session {session_id} closed.")
