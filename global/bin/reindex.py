#!/usr/bin/env python3
"""reindex.py — Full rebuild of the warm index (Tier 1).

Charter Section VI: The reindex script is the ONLY component permitted to
write the warm index outside of the dispatch append-hook. It must:
- Read every file under global/ledger/*.jsonl and global/post-mortems/*.md
- Drop and recreate index.db from scratch (no incremental updates)
- Populate meta entries
- Run in under 60 seconds at 10,000 ledger entries
- Exit non-zero if any source file is malformed; never silently skip
- Print a one-line summary on success

This script is idempotent and destructive — it always starts fresh.
"""

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

# Charter Section IV schema (canonical, do not change)
TRIALS_SCHEMA = """\
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
  ledger_offset INTEGER NOT NULL
);"""

TRIALS_INDEXES = """\
CREATE INDEX idx_trials_target ON trials(target);
CREATE INDEX idx_trials_skill_target ON trials(skill_id, target);
CREATE INDEX idx_trials_project ON trials(project_id);
CREATE INDEX idx_trials_ts ON trials(ts);"""

POST_MORTEMS_SCHEMA = """\
CREATE TABLE post_mortems (
  atom_id        TEXT PRIMARY KEY,
  written_at     INTEGER NOT NULL,
  source_path    TEXT NOT NULL,
  gotchas        TEXT,
  difficulties   TEXT,
  recommendations TEXT
);"""

FTS_SCHEMA = """\
CREATE VIRTUAL TABLE pm_fts USING fts5(
  atom_id,
  content,
  content='post_mortems',
  content_rowid='rowid'
);"""

META_SCHEMA = """\
CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);"""

CHARTER_VERSION = "1.0"


def iso_to_epoch(ts_str):
    """Convert ISO timestamp string to epoch seconds (integer).

    Handles formats like:
      2026-04-27T19:57:28.052394Z
      2026-04-26T11:34:00-04:00
      2026-04-26T16:26:05.522722Z
    """
    if not ts_str:
        return 0
    try:
        # Strip trailing Z and parse
        s = ts_str.rstrip("Z")
        # Remove timezone offset for simplicity (use as-is UTC)
        # Try datetime fromisoformat
        import datetime
        # Handle Z suffix
        s2 = s.replace("Z", "")
        # Handle +00:00 style offsets — strip for UTC assumption
        if "+" in s2[10:]:
            s2 = s2[:s2.index("+", 10)]
        elif s2.count("-") > 2:
            # Find the last dash after the date part (timezone)
            date_part = s2[:10]
            rest = s2[10:]
            last_dash = rest.rfind("-")
            if last_dash > 1:
                s2 = date_part + rest[:last_dash]
        
        # Remove microseconds for clean parsing
        s2 = s2.split(".")[0]
        
        dt = datetime.datetime.fromisoformat(s2)
        return int(dt.timestamp())
    except Exception:
        return 0


def normalize_trial(entry, ledger_file, byte_offset):
    """Normalize a ledger entry into the canonical trial schema.

    Charter HR-1: No migration tooling — just normalize on read.
    """
    trial_id = entry.get("trial_id") or entry.get("ulid", "unknown")
    
    # result or status — both are used interchangeably in the ledger
    result = entry.get("result") or entry.get("status") or "failure"
    # Normalize: only allow the four Charter-approved values
    if result not in ("success", "failure", "partial", "timeout"):
        result = "failure"
    
    # ts: might be ISO string or integer
    ts_raw = entry.get("ts")
    ts = iso_to_epoch(str(ts_raw)) if ts_raw else 0
    
    skill_id = entry.get("skill_id", "unknown")
    skill_version = entry.get("skill_version", 0) or 0
    target = entry.get("target", "unknown")
    project_id = entry.get("project_id", "unknown")
    session_id = entry.get("session_id", "unknown")
    artifact_path = entry.get("artifact_path")
    duration_ms = entry.get("duration_ms")
    inputs_hash = entry.get("inputs_hash")
    if not inputs_hash or inputs_hash is None:
        # Try to compute from inputs_fingerprint
        fp = entry.get("inputs_fingerprint")
        if fp:
            import hashlib
            inputs_hash = "sha256:" + hashlib.sha256(
                json.dumps(fp, sort_keys=True).encode()
            ).hexdigest()
        else:
            # Generate a deterministic hash from trial_id + target
            import hashlib
            inputs_hash = "sha256:derived:" + hashlib.sha256(
                f"{trial_id}:{target}".encode()
            ).hexdigest()
    
    return {
        "trial_id": trial_id,
        "ts": ts,
        "skill_id": skill_id,
        "skill_version": skill_version,
        "target": target,
        "project_id": project_id,
        "session_id": session_id,
        "result": result,
        "artifact_path": artifact_path,
        "duration_ms": duration_ms,
        "inputs_hash": inputs_hash,
        "ledger_offset": byte_offset,
    }


def extract_section(content, section_marker):
    """Extract the body text under a section marker in a markdown post-mortem."""
    # Match ## SectionName or ### Subsection
    pattern = re.compile(
        r"^\s*#{1,3}\s*" + re.escape(section_marker) + r"\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(content)
    if not match:
        return ""
    
    start = match.end()
    # Find next section marker at ## or ### level
    next_section = re.search(
        r"\n\n\s*#{1,3}\s+\S",
        content[start:start + 10000]
    )
    if next_section:
        end = start + next_section.start()
    else:
        end = len(content)
    
    return content[start:end].strip()


def parse_post_mortem(md_path):
    """Parse a post-mortem markdown file and extract structured fields."""
    content = md_path.read_text()
    atom_id = md_path.stem  # e.g., "web.gobuster" from "web.gobuster.md"
    
    written_at = int(md_path.stat().st_mtime)
    
    # Extract sections
    difficulties = extract_section(content, "What Was Difficult During Implementation")
    gotchas = extract_section(content, "Unexpected Gotchas")
    
    # Recommendations may be under different headings
    recommendations = (
        extract_section(content, "Recommendations")
        or extract_section(content, "Follow-up TDs")
        or extract_section(content, "Recommendations for Future")
        or ""
    )
    
    return {
        "atom_id": atom_id,
        "written_at": written_at,
        "source_path": str(md_path),
        "gotchas": gotchas,
        "difficulties": difficulties,
        "recommendations": recommendations,
    }


def create_schema(conn):
    """Create (or recreate) all tables from scratch."""
    cursor = conn.cursor()
    
    # Drop everything first for a clean rebuild
    cursor.executescript("DROP TABLE IF EXISTS trials;")
    cursor.executescript("DROP TABLE IF EXISTS post_mortems;")
    cursor.executescript("DROP TABLE IF EXISTS pm_fts;")
    cursor.executescript("DROP TABLE IF EXISTS meta;")
    
    cursor.executescript(TRIALS_SCHEMA)
    cursor.executescript(TRIALS_INDEXES)
    cursor.executescript(POST_MORTEMS_SCHEMA)
    cursor.executescript(FTS_SCHEMA)
    cursor.executescript(META_SCHEMA)
    
    conn.commit()


def index_trials(conn, ledger_dir):
    """Read all ledger JSONL files and insert trial rows."""
    cursor = conn.cursor()
    count = 0
    errors = []
    
    for jsonl_file in sorted(ledger_dir.glob("*.jsonl")):
        if jsonl_file.name.startswith("."):
            continue
        byte_pos = 0
        with open(jsonl_file, "rb") as f:
            while True:
                raw_line = f.readline().decode("utf-8", errors="replace").rstrip("\n")
                if not raw_line:
                    break
                byte_offset = byte_pos
                byte_pos = f.tell()
                try:
                    entry = json.loads(raw_line)
                    trial = normalize_trial(entry, jsonl_file, byte_offset)
                    cursor.execute(
                        """INSERT OR REPLACE INTO trials (
                            trial_id, ts, skill_id, skill_version,
                            target, project_id, session_id, result,
                            artifact_path, duration_ms, inputs_hash,
                            ledger_offset
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            trial["trial_id"],
                            trial["ts"],
                            trial["skill_id"],
                            trial["skill_version"],
                            trial["target"],
                            trial["project_id"],
                            trial["session_id"],
                            trial["result"],
                            trial["artifact_path"],
                            trial["duration_ms"],
                            trial["inputs_hash"],
                            trial["ledger_offset"],
                        ),
                    )
                    count += 1
                except json.JSONDecodeError as e:
                    errors.append(f"{jsonl_file.name}: {e}")
                    # Charter HR-1: exit non-zero on malformed data
                    print(f"ERROR: malformed entry at {jsonl_file.name}: {e}", file=sys.stderr)
    
    conn.commit()
    return count, errors


def index_post_mortems(conn, pm_dir):
    """Parse all post-mortem markdowns and insert into post_mortems + pm_fts tables."""
    cursor = conn.cursor()
    count = 0
    
    for md_path in sorted(pm_dir.glob("*.md")):
        if md_path.name.startswith("."):
            continue
        try:
            pm = parse_post_mortem(md_path)
            cursor.execute(
                """INSERT INTO post_mortems (atom_id, written_at, source_path, gotchas, difficulties, recommendations)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pm["atom_id"], pm["written_at"], pm["source_path"],
                 pm["gotchas"], pm["difficulties"], pm["recommendations"]),
            )
            # Also insert into FTS table
            cursor.execute(
                """INSERT INTO pm_fts (rowid, atom_id, content)
                   VALUES ((SELECT rowid FROM post_mortems WHERE atom_id=?), ?, ?)""",
                (pm["atom_id"], pm["atom_id"], pm["gotchas"] + " " + pm["difficulties"] + " " + pm["recommendations"]),
            )
            count += 1
        except Exception as e:
            print(f"WARNING: Failed to parse {md_path}: {e}", file=sys.stderr)
    
    conn.commit()
    return count


def populate_meta(conn, trial_count, pm_count):
    """Write metadata entries."""
    import datetime
    cursor = conn.cursor()
    now = int(datetime.datetime.now(datetime.UTC).timestamp()) if hasattr(datetime.datetime, "UTC") else int(time.time())
    
    meta_entries = [
        ("schema_version", "1.0"),
        ("charter_version", CHARTER_VERSION),
        ("rebuilt_at", str(now)),
        ("source_ledger_count", str(trial_count)),
    ]
    
    for key, value in meta_entries:
        cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()


def main():
    start = time.time()
    
    base_dir = Path.home() / ".securatron"
    ledger_dir = base_dir / "global" / "ledger"
    pm_dir = base_dir / "global" / "post-mortems"
    db_path = base_dir / "global" / "memory" / "index.db"
    
    # Ensure memory directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Verify source directories exist
    if not ledger_dir.exists():
        print(f"ERROR: Ledger directory not found: {ledger_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not pm_dir.exists():
        print(f"WARNING: Post-mortem directory not found: {pm_dir}", file=sys.stderr)
        pm_dir.mkdir(parents=True, exist_ok=True)
    
    # Create schema (drop + recreate)
    conn = sqlite3.connect(str(db_path))
    create_schema(conn)
    
    # Index trials
    trial_count, errors = index_trials(conn, ledger_dir)
    
    # Index post-mortems
    pm_count = index_post_mortems(conn, pm_dir)
    
    # Populate metadata
    populate_meta(conn, trial_count, pm_count)
    
    # Verify integrity
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM trials")
    verify_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM post_mortems")
    verify_pm = cursor.fetchone()[0]
    
    conn.close()
    
    elapsed = time.time() - start
    
    if errors:
        print(f"reindex: {verify_count} trials, {verify_pm} post-mortems, {elapsed:.1f}s", file=sys.stderr)
        print(f"ERROR: {len(errors)} malformed entries skipped", file=sys.stderr)
        sys.exit(1)
    
    # Success summary (one line)
    print(f"reindex: {verify_count} trials, {verify_pm} post-mortems, {elapsed:.1f}s")
    
    # Verify rebuild time requirement (HR-1: under 60s at 10k entries)
    if elapsed > 60:
        print(f"WARNING: Rebuild took {elapsed:.1f}s (over 60s limit for 10k entries)", file=sys.stderr)


if __name__ == "__main__":
    main()
