import json
import sqlite3
import hashlib
import os
from pathlib import Path
import time
from datetime import datetime

# Standard paths
BASE_DIR = Path(os.getenv("SECURATRON_HOME", str(Path.home() / ".securatron")))
LEDGER_DIR = BASE_DIR / "global" / "ledger"
POSTMORTEM_DIR = BASE_DIR / "global" / "post-mortems"
DB_PATH = BASE_DIR / "global" / "memory" / "index.db"

SCHEMA_VERSION = "1.1"
CHARTER_VERSION = "1.1"

def inputs_hash(inputs: dict) -> str:
    """Generate a stable SHA-256 hash of the inputs."""
    canonical_json = json.dumps(inputs, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_json).hexdigest()}"

def normalize_trial(skill_id, entry):
    """Normalize ledger entry to the canonical trials schema."""
    # trial_id: trial_id -> ulid (handle both)
    trial_id = entry.get("trial_id") or entry.get("ulid") or entry.get("session_id")
    
    # ts: ts -> timestamp (handle both)
    raw_ts = entry.get("ts") or entry.get("timestamp")
    if isinstance(raw_ts, (int, float)):
        ts = int(raw_ts)
    elif isinstance(raw_ts, str):
        try:
            # Handle common ISO formats
            ts = int(datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp())
        except ValueError:
            ts = int(time.time())
    else:
        ts = int(time.time())

    # inputs_hash: inputs_hash -> hash from inputs_fingerprint (handle both)
    origin = "original"
    h = entry.get("inputs_hash")
    if not h:
        if "inputs_fingerprint" in entry and isinstance(entry["inputs_fingerprint"], dict):
            h = inputs_hash(entry["inputs_fingerprint"])
            origin = "computed"
        else:
            h = f"sha256:derived:{trial_id}:{entry.get('target', 'unknown')}"
            origin = "inferred"

    return {
        "trial_id": trial_id,
        "ts": ts,
        "skill_id": skill_id,
        "skill_version": entry.get("skill_version", 1),
        "target": entry.get("target") or (entry.get("inputs_fingerprint") or {}).get("target", "unknown"),
        "project_id": entry.get("project_id", "unknown"),
        "session_id": entry.get("session_id") or entry.get("ulid", "unknown"),
        "result": entry.get("result") or entry.get("status") or "unknown",
        "artifact_path": entry.get("artifact_path"),
        "duration_ms": entry.get("duration_ms"),
        "inputs_hash": h,
        "hash_origin": origin
    }

def reindex():
    """Drop and recreate the memory index from source files."""
    start_time = time.time()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    if DB_PATH.exists():
        DB_PATH.unlink()
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Section IV Schema
    cursor.execute("""
    CREATE TABLE trials (
      trial_id      TEXT PRIMARY KEY,
      ts            INTEGER NOT NULL,
      skill_id      TEXT NOT NULL,
      skill_version INTEGER NOT NULL,
      target        TEXT NOT NULL,
      project_id    TEXT NOT NULL,
      session_id    TEXT NOT NULL,
      result        TEXT NOT NULL CHECK(result IN ('success','failure','partial','timeout')),
      artifact_path TEXT,
      duration_ms   INTEGER,
      inputs_hash   TEXT NOT NULL,
      hash_origin   TEXT NOT NULL CHECK(hash_origin IN ('original','inferred','computed')),
      ledger_offset INTEGER NOT NULL
    )""")

    cursor.execute("CREATE INDEX idx_trials_target ON trials(target)")
    cursor.execute("CREATE INDEX idx_trials_skill_target ON trials(skill_id, target)")
    cursor.execute("CREATE INDEX idx_trials_project ON trials(project_id)")
    cursor.execute("CREATE INDEX idx_trials_ts ON trials(ts)")

    cursor.execute("""
    CREATE TABLE post_mortems (
      atom_id        TEXT PRIMARY KEY,
      written_at     INTEGER NOT NULL,
      source_path    TEXT NOT NULL,
      gotchas        TEXT,
      difficulties   TEXT,
      recommendations TEXT
    )""")

    cursor.execute("""
    CREATE VIRTUAL TABLE pm_fts USING fts5(
      atom_id,
      content,
      content='post_mortems',
      content_rowid='rowid'
    )""")

    cursor.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    # Index Trials
    total_ledger_entries = 0
    unique_trials = 0
    for jsonl in sorted(LEDGER_DIR.glob("*.trials.jsonl")):
        skill_id = jsonl.name.replace(".trials.jsonl", "")
        with open(jsonl, "rb") as f:
            offset = 0
            for line in f:
                total_ledger_entries += 1
                try:
                    entry = json.loads(line)
                    trial = normalize_trial(skill_id, entry)
                    
                    cursor.execute("""
                    INSERT OR REPLACE INTO trials 
                    (trial_id, ts, skill_id, skill_version, target, project_id, session_id, result, artifact_path, duration_ms, inputs_hash, hash_origin, ledger_offset)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trial["trial_id"], trial["ts"], trial["skill_id"], trial["skill_version"],
                        trial["target"], trial["project_id"], trial["session_id"], trial["result"],
                        trial["artifact_path"], trial["duration_ms"], trial["inputs_hash"], trial["hash_origin"],
                        offset
                    ))
                    unique_trials += cursor.rowcount if cursor.rowcount > 0 else 0
                except (json.JSONDecodeError, sqlite3.Error):
                    continue
                offset += len(line)

    # Index Post-Mortems
    total_post_mortems = 0
    for md_file in sorted(POSTMORTEM_DIR.glob("*.md")):
        content = md_file.read_text()
        atom_id = md_file.stem
        # Simple section extraction
        gotchas = ""
        difficulties = ""
        recommendations = ""
        
        parts = re.split(r"\n## ", content)
        for p in parts:
            if p.lower().startswith("unexpected gotchas"):
                gotchas = p.split("\n", 1)[1].strip()
            elif p.lower().startswith("what was difficult"):
                difficulties = p.split("\n", 1)[1].strip()
            elif p.lower().startswith("recommendations"):
                recommendations = p.split("\n", 1)[1].strip()

        cursor.execute("""
        INSERT INTO post_mortems (atom_id, written_at, source_path, gotchas, difficulties, recommendations)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (atom_id, int(md_file.stat().st_mtime), str(md_file.relative_to(BASE_DIR)), gotchas, difficulties, recommendations))
        
        rowid = cursor.lastrowid
        cursor.execute("INSERT INTO pm_fts (rowid, atom_id, content) VALUES (?, ?, ?)", (rowid, atom_id, content))
        total_post_mortems += 1

    # Meta
    cursor.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("schema_version", SCHEMA_VERSION))
    cursor.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("charter_version", CHARTER_VERSION))
    cursor.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("rebuilt_at", datetime.utcnow().isoformat() + "Z"))
    cursor.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("source_ledger_count", str(total_ledger_entries)))

    conn.commit()
    conn.close()
    
    elapsed = time.time() - start_time
    print(f"reindex: {unique_trials} trials, {total_post_mortems} post-mortems, {elapsed:.1f}s")

if __name__ == "__main__":
    import re
    reindex()
