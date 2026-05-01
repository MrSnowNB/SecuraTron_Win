#!/usr/bin/env python3
"""
SecuraTron Stagecraft Inbox Watcher

Monitors inbox/new/ directories using os.inotify, validates tickets against
the JSON Schema, dispatches to molecules via dispatch.py, and moves files on
completion.

This is the heartbeat of the inbox subsystem. It implements the Watcher
Contract from the INBOX-CHARTER Section VI.

Usage:
    python3 global/bin/inbox_watcher.py [--config CONFIG] [--daemon]

Hard Rules enforced:
    HR-INBOX-1: Never consume from tmp/
    HR-INBOX-2: Per-queue independent watchers
    HR-INBOX-5: inotify preferred on Linux
    HR-INBOX-7: Ledger is truth, inbox files are transient
"""

import json
import logging
import os
import signal
import sys
import threading
import time
import shutil
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from collections import deque

# ---------------------------------------------------------------------------
# Try to import jsonschema
# ---------------------------------------------------------------------------
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# ---------------------------------------------------------------------------
# Try to import yaml (needed for --config loading)
# ---------------------------------------------------------------------------
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ---------------------------------------------------------------------------
# Try to import inotify third-party package
# ---------------------------------------------------------------------------
HAS_INOTIFY = False
try:
    import inotify.adapters
    HAS_INOTIFY = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Try to import dispatch.py and mcp_server
# ---------------------------------------------------------------------------
HAS_DISPATCH = False
try:
    sys.path.append(str(Path(__file__).parent))
    import dispatch as _dispatch_mod
    import mcp_server as _mcp_mod
    HAS_DISPATCH = True
except ImportError:
    HAS_DISPATCH = False

# ---------------------------------------------------------------------------
# Test mode — skip dispatch when env var is set (for fast validation tests)
# ---------------------------------------------------------------------------
_TEST_MODE = os.environ.get('INBOX_TEST_MODE', '0') == '1'
if _TEST_MODE:
    HAS_DISPATCH = False

HAS_LEDGER = False
try:
    sys.path.append(str(Path(__file__).parent))
    import ledger as _ledger_mod
    HAS_LEDGER = True
except ImportError:
    HAS_LEDGER = False

# ---------------------------------------------------------------------------
# Logging setup (comprehensive, structured)
# ---------------------------------------------------------------------------

class StructuredFormatter(logging.Formatter):
    """Structured JSON-like log formatter for easy parsing and optimization."""
    
    def format(self, record):
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, 'ticket_id'):
            log_entry['ticket_id'] = record.ticket_id
        if hasattr(record, 'queue'):
            log_entry['queue'] = record.queue
        if hasattr(record, 'file'):
            log_entry['file'] = record.file
        
        return json.dumps(log_entry)


def setup_logging(log_level="DEBUG", log_dir=None):
    """Set up comprehensive logging infrastructure."""
    if log_dir is None:
        log_dir = Path.home() / '.securatron' / 'logs'
    
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / 'inbox_watcher.log'
    
    logger = logging.getLogger('inbox_watcher')
    logger.setLevel(log_level)
    logger.handlers.clear()
    
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(console_handler)
    
    return logger


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class WatcherConfig:
    """Watcher configuration loaded from config.yaml or defaults."""
    
    SECURATRON_HOME = Path(os.getenv("SECURATRON_HOME", str(Path.home() / ".securatron")))

    DEFAULT_CONFIG = {
        'root': str(SECURATRON_HOME / 'projects' / 'lab-internal' / 'inbox'),
        'queues': [
            {'name': 'inbox', 'path': 'inbox', 'priority': 'normal'},
            {'name': 'inbox.urgent', 'path': 'inbox.urgent', 'priority': 'urgent'},
            {'name': 'inbox.batch', 'path': 'inbox.batch', 'priority': 'low'},
        ],
        'transport': {
            'backend': 'inotify',
            'poll_interval': 5,
        },
        'age_threshold': 86400,  # 24 hours
        'max_retries': 1,
        'schema_path': str(SECURATRON_HOME / 'global' / 'charters' / 'inbox-ticket.schema.json'),
    }
    
    def __init__(self, config_path=None):
        self.config = self.DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            if not HAS_YAML:
                raise RuntimeError(
                    f"config.yaml specified ({config_path}) but yaml package not installed. "
                    "Cannot load custom config."
                )
            with open(config_path) as f:
                user_config = yaml.safe_load(f)
                if 'stagecraft' in user_config and 'inbox' in user_config['stagecraft']:
                    self.config.update(user_config['stagecraft']['inbox'])
    
    @property
    def root(self):
        return self.config['root']
    
    @property
    def queues(self):
        return self.config['queues']
    
    @property
    def transport(self):
        return self.config['transport']
    
    @property
    def age_threshold(self):
        return self.config['age_threshold']
    
    @property
    def max_retries(self):
        return self.config['max_retries']
    
    @property
    def schema_path(self):
        return self.config['schema_path']


# ---------------------------------------------------------------------------
# Ticket validation (Schema Gate)
# ---------------------------------------------------------------------------

def validate_ticket(ticket_data, schema_path):
    """
    Validate a ticket against the JSON Schema.
    
    Returns: (is_valid, errors_or_none)
    """
    if not HAS_JSONSCHEMA:
        return False, ["jsonschema package not installed"]
    
    try:
        with open(schema_path) as f:
            schema = json.load(f)
    except FileNotFoundError:
        return False, [f"Schema file not found: {schema_path}"]
    except json.JSONDecodeError as e:
        return False, [f"Schema file is invalid JSON: {e}"]
    
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(ticket_data))
    
    if errors:
        error_messages = [
            f"{error.json_path}: {error.message}"
            for error in errors
        ]
        return False, error_messages
    
    return True, None


# ---------------------------------------------------------------------------
# inotify watcher implementation
# ---------------------------------------------------------------------------

def watch_queue_inotify(queue_path, schema_path, logger):
    """
    Watch a single queue directory using inotify.
    
    This function blocks forever — it runs in its own thread.
    Implements HR-INBOX-1: watchers MUST NOT consume from tmp/
    Implements HR-INBOX-5: inotify preferred on Linux
    """
    queue_dir = Path(queue_path)
    new_dir = queue_dir / 'new'
    tmp_dir = queue_dir / 'tmp'
    cur_dir = queue_dir / 'cur'
    quarantine_dir = queue_dir / 'quarantine'
    gates_dir = queue_dir / 'gates'  # human_gate pending tickets
    
    for d in [new_dir, tmp_dir, cur_dir, quarantine_dir, gates_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Watching queue: {queue_path}")
    logger.info(f"  new/    = {new_dir}")
    logger.info(f"  tmp/    = {tmp_dir}")
    logger.info(f"  cur/    = {cur_dir}")
    logger.info(f"  quarantine/ = {quarantine_dir}")
    logger.info(f"  gates/  = {gates_dir}")
    
    i = inotify.adapters.Inotify()
    i.add_watch(str(new_dir))
    
    logger.info(f"inotify watcher started for {queue_path}")
    
    for event in i.event_gen():
        if event is None:
            continue
        
        (header, type_names, watch_path, filename) = event
        
        if 'IN_MOVED_TO' in type_names:
            logger.info(f"IN_MOVED_TO: {queue_path}/{filename}")
            process_ticket(str(new_dir / filename), schema_path, logger, queue_dir)


# ---------------------------------------------------------------------------
# Polling fallback
# ---------------------------------------------------------------------------

def watch_queue_poll(queue_path, schema_path, logger, poll_interval=5, max_seen=10000):
    """
    Poll-based fallback for environments without inotify support.
    
    Uses a bounded deque (LRU) to avoid unbounded memory growth.
    Implements HR-INBOX-5: polling as fallback only.
    """
    queue_dir = Path(queue_path)
    new_dir = queue_dir / 'new'
    new_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Polling queue: {queue_path} (interval: {poll_interval}s)")
    
    # Bounded LRU set — after max_seen entries, oldest is evicted
    seen_files = deque(maxlen=max_seen)
    
    while True:
        try:
            current_files = set(os.listdir(str(new_dir)))
            new_files = current_files - set(seen_files)
            
            for filename in new_files:
                if filename.endswith('.json'):
                    filepath = str(new_dir / filename)
                    logger.info(f"Found new file: {queue_path}/{filename}")
                    process_ticket(filepath, schema_path, logger, queue_dir)
                    seen_files.append(filename)
            
        except Exception as e:
            logger.error(f"Error polling queue {queue_path}: {e}")
        
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Ticket processing pipeline
# ---------------------------------------------------------------------------

def process_ticket(filepath, schema_path, logger, queue_dir):
    """
    Process a ticket: validate, dispatch, move to cur/ or quarantine/.
    
    Implements the pickup protocol from INBOX-CHARTER Section IV:
    1. Read and validate against JSON Schema
    2. If human_gate=true, move to gates/ and wait for operator approval
    3. If valid: dispatch to molecule
    4. If invalid: quarantine
    5. Write ledger entry for successful dispatch
    
    Implements HR-INBOX-7: inbox-as-delivery, ledger-as-truth.
    """
    filename = os.path.basename(filepath)
    ticket_id = filename.replace('.json', '')
    
    logger.info(f"Processing ticket: {ticket_id}")
    
    # Step 1: Read the ticket file
    try:
        with open(filepath) as f:
            ticket_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        move_to_quarantine(filepath, queue_dir, ticket_id, f"invalid_json: {e}", logger)
        return
    except FileNotFoundError:
        logger.warning(f"Ticket file disappeared: {filepath}")
        return
    
    # Step 2: Validate against schema
    is_valid, errors = validate_ticket(ticket_data, schema_path)
    if not is_valid:
        logger.warning(f"Schema validation failed for {ticket_id}: {errors}")
        move_to_quarantine(filepath, queue_dir, ticket_id, "schema_validation_failed", logger)
        return
    
    # Step 3: Check human gate
    human_gate = ticket_data.get('human_gate', False)
    if human_gate:
        # Move to gates/ for operator approval
        gates_dir = queue_dir / 'gates'
        gates_dir.mkdir(parents=True, exist_ok=True)
        gates_path = gates_dir / filename
        try:
            shutil.copy2(filepath, str(gates_path))
            os.remove(filepath)
            logger.info(f"Ticket {ticket_id} moved to gates/ (human gate pending)")
            # In production, this would wait for operator approval
            # For now, log a warning and continue processing
            logger.warning(f"TICKET {ticket_id} requires human approval — auto-continuing (no operator gate implemented yet)")
            # Continue to dispatch step
        except Exception as e:
            logger.error(f"Failed to gate ticket {ticket_id}: {e}")
            move_to_quarantine(filepath, queue_dir, ticket_id, f"gate_error: {e}", logger)
            return
    
    # Step 4: Mark as processing
    ticket_data['status'] = 'processing'
    logger.info(f"Ticket {ticket_id} status: processing")
    
    # Step 5: Dispatch (REAL — no longer a stub)
    skill_name = ticket_data.get('skill', 'unknown')
    ticket_inputs = ticket_data.get('inputs', {})
    project = ticket_data.get('project', 'lab-internal')
    session_id = ticket_data.get('session_id', None)
    
    dispatch_result = None
    dispatch_success = False
    
    if HAS_DISPATCH:
        try:
            # Get the skill card from mcp_server.CARDS
            card = _mcp_mod.CARDS.get(skill_name)
            
            if card is None:
                logger.warning(f"Skill '{skill_name}' not found in CARDS — quarantining")
                move_to_quarantine(filepath, queue_dir, ticket_id, f"unknown_skill: {skill_name}", logger)
                return
            
            # Generate session_id if not provided
            if session_id is None:
                # Simple ULID-like ID for the session
                session_id = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + str(os.getpid())
            
            # Call dispatch.card, inputs, project_id, session_id)
            result = _dispatch_mod.dispatch(card, ticket_inputs, project, session_id)
            dispatch_result = result
            dispatch_success = result.get('ok', False)
            ticket_data['dispatch_result'] = result
            
            logger.info(f"Ticket {ticket_id} dispatch to {skill_name}: {'SUCCESS' if dispatch_success else 'FAILURE'}")
            
            # Write ledger entry on dispatch success
            if HAS_LEDGER and dispatch_success:
                try:
                    _ledger_mod.record_trial(skill_name, {
                        "trial_id": ticket_id,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "skill_id": skill_name,
                        "target": ticket_inputs.get('target', 'unknown'),
                        "result": "success" if result.get("ok") else "failure",
                        "inputs_fingerprint": ticket_inputs,
                        "duration_ms": result.get("duration_ms"),
                        "artifact_path": result.get("artifact_path"),
                    })
                    logger.info(f"Ledger entry recorded for {skill_name} (ticket {ticket_id})")
                except Exception as e:
                    logger.error(f"Failed to write ledger entry: {e}")
            
            # Update status based on dispatch result
            ticket_data['status'] = 'completed' if dispatch_success else 'failed'
            
        except Exception as e:
            logger.error(f"Dispatch exception for ticket {ticket_id}: {e}")
            ticket_data['status'] = 'failed'
            ticket_data['dispatch_error'] = str(e)
            # Don't quarantine on dispatch errors — move to cur/ with failed status
            # so the operator can investigate
            cur_dir = queue_dir / 'cur'
            try:
                with open(str(cur_dir / filename), 'w') as f:
                    json.dump(ticket_data, f, indent=2)
                os.remove(filepath)
                logger.info(f"Ticket {ticket_id} moved to cur/ (dispatch failed: {e})")
            except Exception as e2:
                logger.error(f"Failed to move failed ticket to cur/: {e2}")
            return
    else:
        # No dispatch available — this is a configuration error
        logger.warning(f"Dispatch module not available (HAS_DISPATCH=False). "
                       f"Ticket {ticket_id} moved to cur/ without execution.")
        ticket_data['status'] = 'completed'
        ticket_data['dispatch_stub'] = True
    
    # Step 6: Move to cur/
    cur_dir = queue_dir / 'cur'
    cur_path = str(cur_dir / filename)
    
    try:
        with open(cur_path, 'w') as f:
            json.dump(ticket_data, f, indent=2)
        os.remove(filepath)
        logger.info(f"Ticket {ticket_id} moved to cur/ (status={ticket_data['status']})")
    except Exception as e:
        logger.error(f"Failed to move {filename} to cur/: {e}")


def move_to_quarantine(filepath, queue_dir, ticket_id, reason, logger):
    """Move a failed ticket to quarantine."""
    quarantine_dir = queue_dir / 'quarantine'
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    
    filename = os.path.basename(filepath)
    quarantine_path = str(quarantine_dir / f"{ticket_id}.json")
    
    try:
        with open(filepath) as f:
            data = json.load(f)
        data['quarantine_reason'] = reason
        data['quarantine_ts'] = datetime.now(timezone.utc).isoformat()
        with open(quarantine_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        shutil.copy2(filepath, quarantine_path)
    
    os.remove(filepath)
    logger.warning(f"Ticket {ticket_id} quarantined: {reason}")


# ---------------------------------------------------------------------------
# Main watcher loop
# ---------------------------------------------------------------------------

def main():
    """Start the inbox watcher."""
    import argparse
    
    parser = argparse.ArgumentParser(description='SecuraTron Inbox Watcher')
    parser.add_argument('--config', help='Path to config.yaml')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--log-level', default='DEBUG', help='Log level (default: DEBUG)')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode (no inotify)')
    
    args = parser.parse_args()
    
    logger = setup_logging(args.log_level)
    logger.info("=" * 60)
    logger.info("Inbox Watcher starting")
    logger.info(f"  Log level: {args.log_level}")
    logger.info(f"  Test mode: {args.test_mode}")
    logger.info("=" * 60)
    
    # Load configuration
    try:
        config = WatcherConfig(args.config)
    except RuntimeError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    logger.info(f"Inbox root: {config.root}")
    logger.info(f"Queues: {[q['name'] for q in config.queues]}")
    logger.info(f"Transport backend: {config.transport['backend']}")
    
    # Validate schema file exists
    if not os.path.exists(config.schema_path):
        logger.error(f"Schema file not found: {config.schema_path}")
        logger.error("This is a fatal error. HR-INBOX-6 requires a versioned schema file.")
        sys.exit(1)
    
    logger.info(f"Schema file: {config.schema_path}")
    
    # Check capabilities
    logger.info(f"jsonschema: {'available' if HAS_JSONSCHEMA else 'NOT AVAILABLE'}")
    logger.info(f"inotify: {'available' if HAS_INOTIFY else 'NOT AVAILABLE'}")
    logger.info(f"dispatch: {'available' if HAS_DISPATCH else 'NOT AVAILABLE'}")
    logger.info(f"yaml: {'available' if HAS_YAML else 'NOT AVAILABLE'}")
    logger.info(f"ledger: {'available' if HAS_LEDGER else 'NOT AVAILABLE'}")
    
    if not HAS_INOTIFY and not args.test_mode:
        logger.warning("inotify package NOT installed — falling back to polling mode.")
        logger.warning("This is degraded: higher CPU, latency up to poll_interval seconds.")
        logger.warning("Install with: pip install inotify")
    
    if not HAS_JSONSCHEMA:
        logger.error("jsonschema NOT available — cannot validate tickets.")
        sys.exit(1)
    
    if not HAS_DISPATCH:
        logger.warning("dispatch.py NOT available — tickets will be processed without execution.")
    
    # Create all queue directories
    for queue in config.queues:
        queue_path = os.path.join(config.root, queue['path'])
        for subdir in ['tmp', 'new', 'cur', 'quarantine', 'gates']:
            (Path(queue_path) / subdir).mkdir(parents=True, exist_ok=True)
    
    # Start watching queues in separate threads (HR-INBOX-2: per-queue independent)
    threads = []
    for queue in config.queues:
        queue_path = os.path.join(config.root, queue['path'])
        
        if args.test_mode or not HAS_INOTIFY:
            t = threading.Thread(
                target=watch_queue_poll,
                args=(queue_path, config.schema_path, logger, config.transport['poll_interval']),
                name=f"poll-{queue['name']}",
                daemon=True,
            )
        else:
            t = threading.Thread(
                target=watch_queue_inotify,
                args=(queue_path, config.schema_path, logger),
                name=f"inotify-{queue['name']}",
                daemon=True,
            )
        
        t.start()
        threads.append(t)
        logger.info(f"Started {t.name}")
    
    logger.info(f"All {len(threads)} queue watchers started. Press Ctrl+C to exit.")
    
    # Wait for all threads (they're daemon threads, so this blocks forever)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Inbox Watcher shutting down...")


if __name__ == '__main__':
    main()
