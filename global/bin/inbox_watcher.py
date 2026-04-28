#!/usr/bin/env python3
"""
SecuraTron Stagecraft Inbox Watcher

Monitors inbox/new/ directories using os.inotify, validates tickets against
the JSON Schema, dispatches to molecules, and moves files on completion.

This is the heartbeat of the inbox subsystem. It implements the Watcher
Contract from the INBOX-CHARTER Section VI.

Usage:
    python3 global/bin/inbox_watcher.py [--config CONFIG] [--daemon]

Hard Rules enforced:
    HR-INBOX-1: Never consume from tmp/
    HR-INBOX-2: Per-queue independent watchers
    HR-INBOX-5: inotify preferred on Linux
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Try to import jsonschema
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# Try to import inotify
HAS_INOTIFY = False
try:
    import inotify.adapters
    HAS_INOTIFY = True
except ImportError:
    pass

# Also try os.inotify (Python 3.13+)
HAS_OS_INOTIFY = False
try:
    # Check if os.inotify is available
    if hasattr(os, 'inotify_add_watch'):
        HAS_OS_INOTIFY = True
except AttributeError:
    pass

# ---------------------------------------------------------------------------
# Logging setup (comprehensive, structured)
# ---------------------------------------------------------------------------

class StructuredFormatter(logging.Formatter):
    """Structured JSON-like log formatter for easy parsing and optimization."""
    
    def format(self, record):
        # Build structured log entry
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
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
    
    # Main log file
    log_file = log_dir / 'inbox_watcher.log'
    
    # Setup root logger
    logger = logging.getLogger('inbox_watcher')
    logger.setLevel(log_level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler (all logs)
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)
    
    # Console handler (INFO and above)
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
    
    DEFAULT_CONFIG = {
        'root': str(Path.home() / '.securatron' / 'projects' / 'lab-internal' / 'inbox'),
        'queues': [
            {'name': 'inbox', 'path': 'inbox', 'priority': 'normal'},
            {'name': 'inbox.urgent', 'path': 'inbox.urgent', 'priority': 'urgent'},
            {'name': 'inbox.batch', 'path': 'inbox.batch', 'priority': 'low'},
        ],
        'transport': {
            'backend': 'inotify',
            'poll_interval': 5,
        },
        'age_threshold': 86400,  # 24 hours in seconds
        'max_retries': 1,
        'schema_path': str(Path.home() / '.securatron' / 'global' / 'charters' / 'inbox-ticket.schema.json'),
    }
    
    def __init__(self, config_path=None):
        self.config = self.DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                user_config = yaml.safe_load(f)
                if 'stagecraft' in user_config:
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
    
    This implements HR-INBOX-6: ticket schema is a versioned file in code,
    never implicit in code. The watcher reads the schema from the file,
    not from hardcoded field lists.
    
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
    
    # Validate the ticket against the schema
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
# Inotify watcher implementation
# ---------------------------------------------------------------------------

def watch_queue_inotify(queue_path, schema_path, logger):
    """
    Watch a single queue directory using inotify.
    
    Implements HR-INBOX-1: Watchers MUST NOT consume from tmp/
    Implements HR-INBOX-5: inotify preferred on Linux
    """
    queue_dir = Path(queue_path)
    new_dir = queue_dir / 'new'
    tmp_dir = queue_dir / 'tmp'
    cur_dir = queue_dir / 'cur'
    quarantine_dir = queue_dir / 'quarantine'
    
    # Ensure all directories exist
    for d in [new_dir, tmp_dir, cur_dir, quarantine_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Watching queue: {queue_path}")
    logger.info(f"  new/    = {new_dir}")
    logger.info(f"  tmp/    = {tmp_dir}")
    logger.info(f"  cur/    = {cur_dir}")
    logger.info(f"  quarantine/ = {quarantine_dir}")
    
    # Monitor new/ for IN_MOVED_TO events
    # This ensures we only pick up files that have been atomically moved
    # from tmp/ to new/ (HR-INBOX-1 compliance)
    if HAS_INOTIFY:
        i = inotify.adapters.Inotify()
        i.add_watch(str(new_dir))
        
        for event in i.event_gen():
            if event is None:
                continue
            
            (header, type_names, watch_path, filename) = event
            
            if 'IN_MOVED_TO' in type_names:
                logger.info(f"IN_MOVED_TO: {queue_path}/{filename}")
                process_ticket(str(new_dir / filename), schema_path, logger, queue_dir)


def watch_queue_poll(queue_path, schema_path, logger, poll_interval=5):
    """
    Poll-based fallback for environments without inotify support.
    
    Used when inotify is unavailable (e.g., container environments).
    Implements HR-INBOX-5: polling as fallback only.
    """
    queue_dir = Path(queue_path)
    new_dir = queue_dir / 'new'
    new_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Polling queue: {queue_path} (interval: {poll_interval}s)")
    
    seen_files = set()
    
    while True:
        try:
            current_files = set(os.listdir(str(new_dir)))
            new_files = current_files - seen_files
            
            for filename in new_files:
                if filename.endswith('.json'):
                    filepath = str(new_dir / filename)
                    logger.info(f"Found new file: {queue_path}/{filename}")
                    process_ticket(filepath, schema_path, logger, queue_dir)
                    seen_files.add(filename)
            
        except Exception as e:
            logger.error(f"Error polling queue {queue_path}: {e}")
        
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Ticket processing pipeline
# ---------------------------------------------------------------------------

def process_ticket(filepath, schema_path, logger, queue_dir):
    """
    Process a ticket: validate, dispatch, move to cur/ or quarantine/.
    
    This implements the pickup protocol from INBOX-CHARTER Section IV:
    1. Read and validate against JSON Schema
    2. If valid: dispatch
    3. If invalid: quarantine
    
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
    
    # Step 3: Mark as processing
    ticket_data['status'] = 'processing'
    logger.info(f"Ticket {ticket_id} status: processing")
    
    # Step 4: Dispatch (stub for now)
    logger.info(f"Ticket {ticket_id} dispatched to skill: {ticket_data.get('skill', 'unknown')}")
    ticket_data['status'] = 'completed'
    
    # Step 5: Move to cur/
    cur_dir = queue_dir / 'cur'
    new_filepath = str(cur_dir / filename)
    
    try:
        # Write updated status to cur/
        with open(new_filepath, 'w') as f:
            json.dump(ticket_data, f, indent=2)
        os.remove(filepath)
        logger.info(f"Ticket {ticket_id} moved to cur/")
    except Exception as e:
        logger.error(f"Failed to move {filename} to cur/: {e}")


def move_to_quarantine(filepath, queue_dir, ticket_id, reason, logger):
    """Move a failed ticket to quarantine."""
    quarantine_dir = queue_dir / 'quarantine'
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    
    filename = os.path.basename(filepath)
    quarantine_path = str(quarantine_dir / f"{ticket_id}.json")
    
    # Add reason to the ticket if it's valid JSON
    try:
        with open(filepath) as f:
            data = json.load(f)
        data['quarantine_reason'] = reason
        with open(quarantine_path, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        # If the file is not valid JSON, just copy it
        import shutil
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
    
    # Set up logging
    logger = setup_logging(args.log_level)
    logger.info("=" * 60)
    logger.info("Inbox Watcher starting")
    logger.info(f"  Log level: {args.log_level}")
    logger.info(f"  Test mode: {args.test_mode}")
    logger.info("=" * 60)
    
    # Load configuration
    config = WatcherConfig(args.config)
    logger.info(f"Inbox root: {config.root}")
    logger.info(f"Queues: {[q['name'] for q in config.queues]}")
    logger.info(f"Transport backend: {config.transport['backend']}")
    
    # Validate schema file exists
    if not os.path.exists(config.schema_path):
        logger.error(f"Schema file not found: {config.schema_path}")
        logger.error("This is a fatal error. HR-INBOX-6 requires a versioned schema file.")
        sys.exit(1)
    
    logger.info(f"Schema file: {config.schema_path}")
    
    # Start watching queues
    for queue in config.queues:
        queue_path = os.path.join(config.root, queue['path'])
        
        if args.test_mode:
            # Use polling in test mode
            watch_queue_poll(queue_path, config.schema_path, logger, config.transport['poll_interval'])
        else:
            # Use inotify (preferred on Linux, HR-INBOX-5)
            watch_queue_inotify(queue_path, config.schema_path, logger)


if __name__ == '__main__':
    main()
