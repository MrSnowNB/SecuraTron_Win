#!/usr/bin/env python3
"""
SecuraTron Stagecraft Inbox — Gated Validation Test Suite

This is the first recursive build test framework for the entire SecuraTron
Stagecraft inbox subsystem. It validates each build step independently,
with gates that can fail the build if something is wrong.

Test phases (each is a gate):
    PHASE-0: Schema file integrity
    PHASE-1: Directory structure
    PHASE-2: Schema validation (valid and invalid tickets)
    PHASE-3: Ticket generation
    PHASE-4: Watcher integration (file-based, no inotify)
    PHASE-5: End-to-end pipeline (produce → validate → dispatch → ledger)

Usage:
    python3 global/bin/test_inbox_validation.py [--phase PHASE] [--verbose]
    python3 global/bin/test_inbox_validation.py --all       (run all phases)

Environment variables:
    INBOX_TEST_LOG_DIR  Override default log directory (default: ~/.securatron/logs/tests/)
    INBOX_TEST_ROOT     Override inbox root (default: ~/.securatron/projects/lab-internal/inbox/)

Exit codes:
    0  All phases pass
    1  One or more phases fail
    2  Test infrastructure error
"""

import json
import logging
import os
import sys
import time
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INBOX_ROOT = os.environ.get(
    'INBOX_TEST_ROOT',
    str(Path.home() / '.securatron' / 'projects' / 'lab-internal' / 'inbox')
)

LOG_DIR = os.environ.get(
    'INBOX_TEST_LOG_DIR',
    str(Path.home() / '.securatron' / 'logs' / 'tests')
)

SCHEMA_PATH = str(Path.home() / '.securatron' / 'global' / 'charters' / 'inbox-ticket.schema.json')

CHARTER_PATH = str(Path.home() / '.securatron' / 'global' / 'charters' / 'INBOX-CHARTER.md')

WATCHER_PATH = str(Path.home() / '.securatron' / 'global' / 'bin' / 'inbox_watcher.py')

LEDER_DIR = str(Path.home() / '.securatron' / 'global' / 'ledger')

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

class TestLogger:
    """Comprehensive test logger that logs everything for debugging and optimization."""
    
    def __init__(self, log_dir, test_name):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.test_name = test_name
        self.log_file = self.log_dir / f"{test_name}.log"
        self.results_file = self.log_dir / f"{test_name}_results.json"
        
        # Setup logger
        self.logger = logging.getLogger(f"test.{test_name}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        # File handler (structured JSON)
        fh = logging.FileHandler(str(self.log_file))
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.logger.addHandler(fh)
        
        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        self.logger.addHandler(ch)
        
        # Test results tracking
        self.results = {
            'test_name': test_name,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'phases': [],
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'warnings': 0,
        }
    
    def info(self, msg, **kwargs):
        self.logger.info(msg, extra=kwargs)
    
    def warning(self, msg, **kwargs):
        self.logger.warning(msg, extra=kwargs)
        self.results['warnings'] += 1
    
    def error(self, msg, **kwargs):
        self.logger.error(msg, extra=kwargs)
    
    def phase_start(self, phase_name):
        self.info(f"=== PHASE START: {phase_name} ===")
        self.results['phases'].append({
            'name': phase_name,
            'start_time': datetime.now(timezone.utc).isoformat(),
            'tests': [],
            'status': 'running',
        })
    
    def phase_end(self, phase_name, status='pass'):
        self.info(f"=== PHASE END: {phase_name} ({status}) ===")
        if self.results['phases']:
            self.results['phases'][-1]['status'] = status
            self.results['phases'][-1]['end_time'] = datetime.now(timezone.utc).isoformat()
    
    def test(self, name, condition, details=''):
        self.results['total_tests'] += 1
        result = {
            'name': name,
            'passed': condition,
            'details': details,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        
        if self.results['phases']:
            self.results['phases'][-1]['tests'].append(result)
        
        if condition:
            self.results['passed'] += 1
            self.info(f"  PASS: {name}")
        else:
            self.results['failed'] += 1
            self.error(f"  FAIL: {name} — {details}")
        
        return condition
    
    def write_results(self):
        with open(self.results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        self.info(f"Results written to: {self.results_file}")
    
    def get_summary(self):
        total = self.results['total_tests']
        passed = self.results['passed']
        failed = self.results['failed']
        return f"Results: {passed}/{total} passed, {failed}/{total} failed"


# ---------------------------------------------------------------------------
# Phase 0: Schema File Integrity
# ---------------------------------------------------------------------------

def phase_0_schema_integrity(test_log):
    """
    Validate the schema file exists, is valid JSON, and has correct structure.
    
    Gates:
        - Schema file must exist
        - Schema file must be valid JSON
        - Schema must have $schema field (draft 2020-12)
        - Schema must have $id field
        - Schema must have required fields matching charter Section V
    """
    test_log.phase_start("Schema File Integrity (PHASE-0)")
    
    # Check file exists
    schema_exists = os.path.exists(SCHEMA_PATH)
    test_log.test("Schema file exists", schema_exists,
                  f"Expected: {SCHEMA_PATH}")
    
    if not schema_exists:
        test_log.phase_end("Schema File Integrity", 'fail')
        test_log.write_results()
        return False
    
    # Check valid JSON
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        test_log.test("Schema file is valid JSON", True)
    except json.JSONDecodeError as e:
        test_log.test("Schema file is valid JSON", False, str(e))
        test_log.phase_end("Schema File Integrity", 'fail')
        test_log.write_results()
        return False
    
    # Check $schema field (draft 2020-12)
    has_schema_field = schema.get('$schema') == 'https://json-schema.org/draft/2020-12/schema'
    test_log.test("$schema field = draft 2020-12", has_schema_field,
                  f"Found: {schema.get('$schema', 'MISSING')}")
    
    # Check $id field
    has_id_field = '$id' in schema and schema['$id'].startswith('securatron/inbox-ticket/')
    test_log.test("$id field starts with securatron/inbox-ticket/", has_id_field,
                  f"Found: {schema.get('$id', 'MISSING')}")
    
    # Check required fields
    required = schema.get('required', [])
    expected_required = ['ticket_id', 'source', 'skill', 'priority', 'created_at', 'status']
    has_all_required = all(field in required for field in expected_required)
    test_log.test("All required fields present", has_all_required,
                  f"Expected: {expected_required}, Found: {required}")
    
    # Check additionalProperties: false (strict schema)
    strict_schema = schema.get('additionalProperties') == False
    test_log.test("additionalProperties = false (strict schema)", strict_schema,
                  f"Found: {schema.get('additionalProperties', 'MISSING')}")
    
    # Check allOf constraint (destructive implies human_gate)
    has_allof_constraint = 'allOf' in schema
    test_log.test("allOf constraint (destructive → human_gate)", has_allof_constraint,
                  f"Found: {'allOf' in schema}")
    
    # Check definitions exist
    has_definitions = 'definitions' in schema
    test_log.test("Schema has definitions block", has_definitions,
                  f"Found definitions: {list(schema.get('definitions', {}).keys())}")
    
    # Check ticket_id pattern
    if 'definitions' in schema and 'ticket_id' in schema['definitions']:
        ticket_id_def = schema['definitions']['ticket_id']
        has_pattern = 'pattern' in ticket_id_def and ticket_id_def['pattern'].startswith('^TICK-')
        test_log.test("ticket_id pattern starts with TICK-", has_pattern,
                      f"Pattern: {ticket_id_def.get('pattern', 'MISSING')}")
    else:
        test_log.test("ticket_id pattern starts with TICK-", False, "ticket_id definition missing")
    
    # Check priority enum
    if 'definitions' in schema and 'priority' in schema['definitions']:
        priority_def = schema['definitions']['priority']
        expected_priorities = ['low', 'normal', 'high', 'urgent']
        has_correct_enum = priority_def.get('enum') == expected_priorities
        test_log.test("priority enum matches charter", has_correct_enum,
                      f"Found: {priority_def.get('enum', 'MISSING')}")
    else:
        test_log.test("priority enum matches charter", False, "priority definition missing")
    
    # Check status enum
    if 'definitions' in schema and 'status' in schema['definitions']:
        status_def = schema['definitions']['status']
        expected_statuses = ['pending', 'processing', 'completed', 'failed', 'quarantined']
        has_correct_enum = status_def.get('enum') == expected_statuses
        test_log.test("status enum matches charter", has_correct_enum,
                      f"Found: {status_def.get('enum', 'MISSING')}")
    else:
        test_log.test("status enum matches charter", False, "status definition missing")
    
    # Check source enum
    if 'definitions' in schema and 'source' in schema['definitions']:
        source_def = schema['definitions']['source']
        expected_sources = ['agent', 'operator', 'mesh', 'external', 'cron']
        has_correct_enum = source_def.get('enum') == expected_sources
        test_log.test("source enum matches charter", has_correct_enum,
                      f"Found: {source_def.get('enum', 'MISSING')}")
    else:
        test_log.test("source enum matches charter", False, "source definition missing")
    
    # Check auth field exists (reserved for CA96)
    has_auth_field = 'auth' in schema.get('properties', {})
    test_log.test("auth field reserved (CA96 future)", has_auth_field,
                  "auth field present in properties")
    
    test_log.phase_end("Schema File Integrity")
    test_log.write_results()
    
    return test_log.results['failed'] == 0


# ---------------------------------------------------------------------------
# Phase 1: Directory Structure
# ---------------------------------------------------------------------------

def phase_1_directory_structure(test_log):
    """
    Validate the inbox directory structure exists with correct layout.
    
    Gates:
        - Inbox root must exist
        - Each queue must have tmp/, new/, cur/, quarantine/
        - Default queues must exist (inbox, inbox.urgent, inbox.batch)
    """
    test_log.phase_start("Directory Structure (PHASE-1)")
    
    # Check inbox root
    root_exists = os.path.exists(INBOX_ROOT)
    test_log.test("Inbox root exists", root_exists,
                  f"Expected: {INBOX_ROOT}")
    
    if not root_exists:
        test_log.phase_end("Directory Structure", 'fail')
        test_log.write_results()
        return False
    
    # Check default queues
    expected_queues = ['inbox', 'inbox.urgent', 'inbox.batch']
    expected_subdirs = ['tmp', 'new', 'cur', 'quarantine']
    
    for queue_name in expected_queues:
        queue_path = os.path.join(INBOX_ROOT, queue_name)
        
        for subdir in expected_subdirs:
            subdir_path = os.path.join(queue_path, subdir)
            exists = os.path.exists(subdir_path) and os.path.isdir(subdir_path)
            test_log.test(f"Queue '{queue_name}/{subdir}/' exists", exists,
                          f"Expected: {subdir_path}")
    
    # Check charter file exists
    charter_exists = os.path.exists(CHARTER_PATH)
    test_log.test("Charter file exists", charter_exists,
                  f"Expected: {CHARTER_PATH}")
    
    # Check watcher script exists
    watcher_exists = os.path.exists(WATCHER_PATH)
    test_log.test("Watcher script exists", watcher_exists,
                  f"Expected: {WATCHER_PATH}")
    
    test_log.phase_end("Directory Structure")
    test_log.write_results()
    
    return test_log.results['failed'] == 0


# ---------------------------------------------------------------------------
# Phase 2: Schema Validation (valid and invalid tickets)
# ---------------------------------------------------------------------------

def phase_2_schema_validation(test_log):
    """
    Validate that the schema correctly accepts valid tickets and rejects invalid ones.
    
    Gates:
        - Valid ticket passes schema validation
        - Missing required field fails validation
        - Invalid priority fails validation
        - Invalid status fails validation
        - Invalid ticket_id format fails validation
        - destructive=true without human_gate=true fails validation
        - Extra unknown fields fail validation (additionalProperties: false)
    """
    test_log.phase_start("Schema Validation (PHASE-2)")
    
    try:
        import jsonschema
    except ImportError:
        test_log.test("jsonschema package available", False, "pip install jsonschema required")
        test_log.phase_end("Schema Validation", 'fail')
        test_log.write_results()
        return False
    
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
    except Exception as e:
        test_log.test("Schema file loadable", False, str(e))
        test_log.phase_end("Schema Validation", 'fail')
        test_log.write_results()
        return False
    
    validator = jsonschema.Draft202012Validator(schema)
    
    # Valid ticket
    valid_ticket = {
        "ticket_id": "TICK-DEAD0001",
        "source": "agent",
        "skill": "web.nikto",
        "target": "scanme.nmap.org",
        "priority": "normal",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
        "human_gate": False,
        "destructive": False,
    }
    
    # Test valid ticket passes
    valid_errors = list(validator.iter_errors(valid_ticket))
    test_log.test("Valid ticket passes schema validation", len(valid_errors) == 0,
                  f"Errors: {[e.message for e in valid_errors]}")
    
    # Missing required field: ticket_id
    missing_ticket_id = {k: v for k, v in valid_ticket.items() if k != 'ticket_id'}
    missing_id_errors = list(validator.iter_errors(missing_ticket_id))
    test_log.test("Missing ticket_id fails validation", len(missing_id_errors) > 0,
                  f"Errors: {[e.message for e in missing_id_errors]}")
    
    # Invalid priority
    bad_priority = valid_ticket.copy()
    bad_priority['priority'] = 'critical'
    bad_priority_errors = list(validator.iter_errors(bad_priority))
    test_log.test("Invalid priority fails validation", len(bad_priority_errors) > 0,
                  f"Errors: {[e.message for e in bad_priority_errors]}")
    
    # Invalid status
    bad_status = valid_ticket.copy()
    bad_status['status'] = 'cancelled'
    bad_status_errors = list(validator.iter_errors(bad_status))
    test_log.test("Invalid status fails validation", len(bad_status_errors) > 0,
                  f"Errors: {[e.message for e in bad_status_errors]}")
    
    # Invalid ticket_id format
    bad_ticket_id = valid_ticket.copy()
    bad_ticket_id['ticket_id'] = "TICK-INVALID"
    bad_id_errors = list(validator.iter_errors(bad_ticket_id))
    test_log.test("Invalid ticket_id format fails validation", len(bad_id_errors) > 0,
                  f"Errors: {[e.message for e in bad_id_errors]}")
    
    # destructive=true without human_gate=true (allOf constraint)
    destructive_no_gate = valid_ticket.copy()
    destructive_no_gate['destructive'] = True
    destructive_no_gate['human_gate'] = False
    destructive_errors = list(validator.iter_errors(destructive_no_gate))
    test_log.test("destructive=true without human_gate=true fails validation", 
                  len(destructive_errors) > 0,
                  f"Errors: {[e.message for e in destructive_errors]}")
    
    # Extra unknown field (additionalProperties: false)
    extra_field = valid_ticket.copy()
    extra_field['unknown_field'] = 'this should fail'
    extra_errors = list(validator.iter_errors(extra_field))
    test_log.test("Extra unknown field fails validation", len(extra_errors) > 0,
                  f"Errors: {[e.message for e in extra_errors]}")
    
    # Valid ticket with inputs (arbitrary object)
    ticket_with_inputs = valid_ticket.copy()
    ticket_with_inputs['inputs'] = {"timeout": 30, "threads": 5}
    inputs_errors = list(validator.iter_errors(ticket_with_inputs))
    test_log.test("Valid ticket with arbitrary inputs passes", len(inputs_errors) == 0,
                  f"Errors: {[e.message for e in inputs_errors]}")
    
    # Valid ticket with destructive=true and human_gate=true
    valid_destructive = valid_ticket.copy()
    valid_destructive['destructive'] = True
    valid_destructive['human_gate'] = True
    valid_destructive_errors = list(validator.iter_errors(valid_destructive))
    test_log.test("destructive=true with human_gate=true passes validation", 
                  len(valid_destructive_errors) == 0,
                  f"Errors: {[e.message for e in valid_destructive_errors]}")
    
    test_log.phase_end("Schema Validation")
    test_log.write_results()
    
    return test_log.results['failed'] == 0


# ---------------------------------------------------------------------------
# Phase 3: Ticket Generation
# ---------------------------------------------------------------------------

def phase_3_ticket_generation(test_log):
    """
    Test ticket generation — write valid and invalid tickets to tmp/ and new/.
    
    Gates:
        - Can write valid ticket to tmp/ → new/
        - File is complete after mv (no partial writes)
        - Invalid ticket can be quarantined
    """
    test_log.phase_start("Ticket Generation (PHASE-3)")
    
    import shutil
    
    # Clean up test directories
    for queue in ['inbox', 'inbox.urgent', 'inbox.batch']:
        for subdir in ['tmp', 'new', 'cur', 'quarantine']:
            dir_path = os.path.join(INBOX_ROOT, queue, subdir)
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
            os.makedirs(dir_path, exist_ok=True)
    
    # Test 1: Write valid ticket to tmp/ → mv to new/
    test_ticket = {
        "ticket_id": "TICK-CC407170",
        "source": "agent",
        "skill": "web.nikto",
        "target": "scanme.nmap.org",
        "priority": "normal",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
        "human_gate": False,
        "destructive": False,
    }
    
    tmp_dir = os.path.join(INBOX_ROOT, 'inbox', 'tmp')
    new_dir = os.path.join(INBOX_ROOT, 'inbox', 'new')
    
    tmp_file = os.path.join(tmp_dir, "TICK-CC407170.json")
    new_file = os.path.join(new_dir, "TICK-CC407170.json")
    
    # Write to tmp/
    with open(tmp_file, 'w') as f:
        json.dump(test_ticket, f, indent=2)
    test_log.test("Valid ticket written to tmp/", True, f"File: {tmp_file}")
    
    # mv to new/
    import shutil
    shutil.move(tmp_file, new_file)
    test_log.test("Ticket moved to new/ (atomic publish)", os.path.exists(new_file),
                  f"tmp exists: {os.path.exists(tmp_file)}, new exists: {os.path.exists(new_file)}")
    
    # Verify file is complete (valid JSON)
    try:
        with open(new_file) as f:
            data = json.load(f)
        test_log.test("Ticket file is complete JSON after mv", True,
                      f"ticket_id: {data.get('ticket_id')}")
    except json.JSONDecodeError:
        test_log.test("Ticket file is complete JSON after mv", False, "Partial write detected")
    
    # Test 2: Write invalid ticket (bad priority) to new/
    bad_ticket = {
        "ticket_id": "TICK-FD9C2C70",
        "source": "agent",
        "skill": "web.nikto",
        "target": "scanme.nmap.org",
        "priority": "critical",  # invalid
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
    }
    
    bad_file = os.path.join(new_dir, "TICK-FD9C2C70.json")
    with open(bad_file, 'w') as f:
        json.dump(bad_ticket, f, indent=2)
    test_log.test("Invalid ticket written to new/", True,
                  "For quarantine testing")
    
    # Test 3: Write destructive ticket (should trigger human_gate)
    destructive_ticket = {
        "ticket_id": "TICK-B1413E2B",
        "source": "operator",
        "skill": "system.delete",
        "target": "/tmp/test-data",
        "priority": "high",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
        "destructive": True,
        "human_gate": True,  # must be true when destructive
    }
    
    dest_file = os.path.join(new_dir, "TICK-B1413E2B.json")
    with open(dest_file, 'w') as f:
        json.dump(destructive_ticket, f, indent=2)
    test_log.test("Destructive ticket with human_gate written to new/", True,
                  "For human-gate testing")
    
    # Test 4: Write urgent ticket
    urgent_ticket = {
        "ticket_id": "TICK-23BF67AF",
        "source": "agent",
        "skill": "recon.gobuster",
        "target": "example.com",
        "priority": "urgent",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
    }
    
    urgent_file = os.path.join(INBOX_ROOT, 'inbox.urgent', 'new', "TICK-23BF67AF.json")
    with open(urgent_file, 'w') as f:
        json.dump(urgent_ticket, f, indent=2)
    test_log.test("Urgent ticket written to inbox.urgent/new/", True,
                  f"File: {urgent_file}")
    
    test_log.phase_end("Ticket Generation")
    test_log.write_results()
    
    return test_log.results['failed'] == 0


# ---------------------------------------------------------------------------
# Phase 4: Watcher Integration (file-based, no inotify)
# ---------------------------------------------------------------------------

def phase_4_watcher_integration(test_log):
    """
    Test the watcher's ticket processing pipeline without inotify.
    
    This tests the core processing logic:
    1. Read ticket from new/
    2. Validate against schema
    3. Move valid tickets to cur/
    4. Move invalid tickets to quarantine/
    
    Gates:
        - Valid ticket in new/ is moved to cur/
        - Invalid ticket in new/ is moved to quarantine/
        - Ticket status is updated to 'processing' then 'completed'
        - Quarantine reason is recorded
    """
    test_log.phase_start("Watcher Integration (PHASE-4)")
    
    import importlib.util
    
    # Load the watcher module
    spec = importlib.util.spec_from_file_location(
        "inbox_watcher", WATCHER_PATH
    )
    try:
        watcher_module = importlib.util.module_for_spec(spec)
    except AttributeError:
        # Python 3.13+ compatibility: use module_from_spec
        watcher_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watcher_module)
    
    # Test validate_ticket function
    if hasattr(watcher_module, 'validate_ticket'):
        # Test valid ticket
        valid_ticket = {
            "ticket_id": "TICK-6676AC9D",
            "source": "agent",
            "skill": "web.nikto",
            "priority": "normal",
            "created_at": "2026-04-27T21:00:00Z",
            "status": "pending",
        }
        
        is_valid, errors = watcher_module.validate_ticket(valid_ticket, SCHEMA_PATH)
        test_log.test("validate_ticket accepts valid ticket", is_valid,
                      f"Errors: {errors}")
        
        # Test invalid ticket
        invalid_ticket = {
            "ticket_id": "TICK-D27CCA4C",
            "source": "agent",
            "skill": "web.nikto",
            "priority": "invalid",
            "created_at": "2026-04-27T21:00:00Z",
            "status": "pending",
        }
        
        is_valid, errors = watcher_module.validate_ticket(invalid_ticket, SCHEMA_PATH)
        test_log.test("validate_ticket rejects invalid ticket", not is_valid,
                      f"Errors: {errors}")
        
        # Test missing required field
        missing_ticket = {
            "ticket_id": "TICK-5FA0785C",
            "source": "agent",
            # missing 'skill'
            "priority": "normal",
            "created_at": "2026-04-27T21:00:00Z",
            "status": "pending",
        }
        
        is_valid, errors = watcher_module.validate_ticket(missing_ticket, SCHEMA_PATH)
        test_log.test("validate_ticket rejects missing required field", not is_valid,
                      f"Errors: {errors}")
        
    else:
        test_log.test("validate_ticket function exists", False,
                      "inbox_watcher.py missing validate_ticket function")
    
    # Test process_ticket function (if it exists)
    if hasattr(watcher_module, 'process_ticket'):
        # Set up fresh test environment
        import shutil
        new_dir = os.path.join(INBOX_ROOT, 'inbox', 'new')
        cur_dir = os.path.join(INBOX_ROOT, 'inbox', 'cur')
        quarantine_dir = os.path.join(INBOX_ROOT, 'inbox', 'quarantine')
        
        # Clean test files
        for f in os.listdir(new_dir):
            os.remove(os.path.join(new_dir, f))
        for f in os.listdir(cur_dir):
            os.remove(os.path.join(cur_dir, f))
        for f in os.listdir(quarantine_dir):
            os.remove(os.path.join(quarantine_dir, f))
        
        # Write a valid ticket
        valid_file = os.path.join(new_dir, "TICK-A0BBD954.json")
        with open(valid_file, 'w') as f:
            json.dump(valid_ticket, f, indent=2)
        
        # Create a logger for the test
        test_logger = logging.getLogger('test.watcher')
        if not test_logger.handlers:
            test_logger.addHandler(logging.StreamHandler(sys.stdout))
        
        watcher_module.process_ticket(valid_file, SCHEMA_PATH, test_logger,
                                      Path(INBOX_ROOT) / 'inbox')
        
        # Check that valid ticket moved to cur/
        cur_file = os.path.join(cur_dir, "TICK-A0BBD954.json")
        test_log.test("Valid ticket moved to cur/", os.path.exists(cur_file),
                      f"cur exists: {os.path.exists(cur_file)}, new exists: {os.path.exists(valid_file)}")
        
        # Check status was updated
        if os.path.exists(cur_file):
            with open(cur_file) as f:
                data = json.load(f)
            test_log.test("Ticket status updated to 'completed'", 
                          data.get('status') == 'completed',
                          f"Status: {data.get('status')}")
        
        # Write an invalid ticket
        invalid_file = os.path.join(new_dir, "TICK-7FFB138C.json")
        with open(invalid_file, 'w') as f:
            json.dump({"ticket_id": "TICK-7FFB138C", "priority": "invalid",
                       "source": "agent", "skill": "web.nikto",
                       "created_at": "2026-04-27T21:00:00Z", "status": "pending"},
                      f, indent=2)
        
        watcher_module.process_ticket(invalid_file, SCHEMA_PATH, test_logger,
                                      Path(INBOX_ROOT) / 'inbox')
        
        # Check that invalid ticket moved to quarantine/
        quarantine_file = os.path.join(quarantine_dir, "TICK-7FFB138C.json")
        test_log.test("Invalid ticket moved to quarantine/", os.path.exists(quarantine_file),
                      f"quarantine exists: {os.path.exists(quarantine_file)}")
        
        # Check quarantine reason was recorded
        if os.path.exists(quarantine_file):
            with open(quarantine_file) as f:
                data = json.load(f)
            has_reason = 'quarantine_reason' in data
            test_log.test("Quarantine reason recorded", has_reason,
                          f"Reason: {data.get('quarantine_reason')}")
    
    else:
        test_log.test("process_ticket function exists", False,
                      "inbox_watcher.py missing process_ticket function")
    
    test_log.phase_end("Watcher Integration")
    test_log.write_results()
    
    return test_log.results['failed'] == 0


# ---------------------------------------------------------------------------
# Phase 5: End-to-End Pipeline
# ---------------------------------------------------------------------------

def phase_5_end_to_end(test_log):
    """
    End-to-end pipeline test: produce → validate → dispatch → ledger.
    
    Gates:
        - Producer can create valid ticket and mv to new/
        - Watcher can process the ticket
        - Ticket moves from new/ → cur/ (valid) or quarantine/ (invalid)
        - Result is logged
        - Pipeline handles multiple queues
    """
    test_log.phase_start("End-to-End Pipeline (PHASE-5)")
    
    import shutil
    
    # Clean all test directories
    for queue in ['inbox', 'inbox.urgent', 'inbox.batch']:
        for subdir in ['tmp', 'new', 'cur', 'quarantine']:
            dir_path = os.path.join(INBOX_ROOT, queue, subdir)
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)
            os.makedirs(dir_path, exist_ok=True)
    
    # Step 1: Producer creates valid ticket
    valid_ticket = {
        "ticket_id": "TICK-0F16930A",
        "source": "agent",
        "skill": "web.nikto",
        "target": "scanme.nmap.org",
        "priority": "normal",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
        "human_gate": False,
        "destructive": False,
        "inputs": {"threads": 5},
    }
    
    tmp_dir = os.path.join(INBOX_ROOT, 'inbox', 'tmp')
    new_dir = os.path.join(INBOX_ROOT, 'inbox', 'new')
    
    tmp_file = os.path.join(tmp_dir, "TICK-0F16930A.json")
    with open(tmp_file, 'w') as f:
        json.dump(valid_ticket, f, indent=2)
    test_log.test("Producer: ticket written to tmp/", True, f"File: {tmp_file}")
    
    # Step 2: Producer publishes (mv to new/)
    new_file = os.path.join(new_dir, "TICK-0F16930A.json")
    shutil.move(tmp_file, new_file)
    test_log.test("Producer: ticket published (mv to new/)", os.path.exists(new_file),
                  "Atomic publish complete")
    
    # Step 3: Watcher processes (import and call process_ticket)
    import importlib.util
    spec = importlib.util.spec_from_file_location("inbox_watcher", WATCHER_PATH)
    try:
        watcher_mod = importlib.util.module_for_spec(spec)
    except AttributeError:
        watcher_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watcher_mod)
    
    # Create a logger
    logger = logging.getLogger('test.e2e')
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler(sys.stdout))
    
    watcher_mod.process_ticket(new_file, SCHEMA_PATH, logger,
                               Path(INBOX_ROOT) / 'inbox')
    
    # Step 4: Check result — ticket should be in cur/
    cur_dir = os.path.join(INBOX_ROOT, 'inbox', 'cur')
    cur_file = os.path.join(cur_dir, "TICK-0F16930A.json")
    test_log.test("End-to-end: valid ticket in cur/", os.path.exists(cur_file),
                  f"cur exists: {os.path.exists(cur_file)}, new exists: {os.path.exists(new_file)}")
    
    # Step 5: Check ticket status was updated
    if os.path.exists(cur_file):
        with open(cur_file) as f:
            data = json.load(f)
        test_log.test("End-to-end: status updated to 'completed'",
                      data.get('status') == 'completed',
                      f"Status: {data.get('status')}")
    
    # Step 6: Test urgent queue
    urgent_ticket = {
        "ticket_id": "TICK-EB13267F",
        "source": "agent",
        "skill": "recon.gobuster",
        "target": "example.com",
        "priority": "urgent",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
    }
    
    urgent_tmp = os.path.join(INBOX_ROOT, 'inbox.urgent', 'tmp', "TICK-EB13267F.json")
    with open(urgent_tmp, 'w') as f:
        json.dump(urgent_ticket, f, indent=2)
    
    urgent_new = os.path.join(INBOX_ROOT, 'inbox.urgent', 'new', "TICK-EB13267F.json")
    shutil.move(urgent_tmp, urgent_new)
    test_log.test("End-to-end: urgent ticket published to inbox.urgent/new/", True)
    
    watcher_mod.process_ticket(urgent_new, SCHEMA_PATH, logger,
                               Path(INBOX_ROOT) / 'inbox.urgent')
    
    urgent_cur = os.path.join(INBOX_ROOT, 'inbox.urgent', 'cur', "TICK-EB13267F.json")
    test_log.test("End-to-end: urgent ticket in inbox.urgent/cur/",
                  os.path.exists(urgent_cur))
    
    # Step 7: Test destructive ticket (human_gate)
    destructive_ticket = {
        "ticket_id": "TICK-75C8AE03",
        "source": "operator",
        "skill": "system.delete",
        "target": "/tmp/test-data",
        "priority": "high",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
        "destructive": True,
        "human_gate": True,
    }
    
    dest_new = os.path.join(INBOX_ROOT, 'inbox', 'new', "TICK-75C8AE03.json")
    with open(dest_new, 'w') as f:
        json.dump(destructive_ticket, f, indent=2)
    
    watcher_mod.process_ticket(dest_new, SCHEMA_PATH, logger,
                               Path(INBOX_ROOT) / 'inbox')
    
    dest_cur = os.path.join(INBOX_ROOT, 'inbox', 'cur', "TICK-75C8AE03.json")
    test_log.test("End-to-end: destructive ticket with human_gate processed",
                  os.path.exists(dest_cur),
                  f"cur exists: {os.path.exists(dest_cur)}")
    
    if os.path.exists(dest_cur):
        with open(dest_cur) as f:
            data = json.load(f)
        test_log.test("End-to-end: destructive ticket has destructive=True",
                      data.get('destructive') == True,
                      f"destructive: {data.get('destructive')}")
    
    # Step 8: Test batch queue
    batch_ticket = {
        "ticket_id": "TICK-9621916A",
        "source": "cron",
        "skill": "recon.gobuster",
        "target": "example.com",
        "priority": "low",
        "created_at": "2026-04-27T21:00:00Z",
        "status": "pending",
    }
    
    batch_new = os.path.join(INBOX_ROOT, 'inbox.batch', 'new', "TICK-9621916A.json")
    with open(batch_new, 'w') as f:
        json.dump(batch_ticket, f, indent=2)
    
    watcher_mod.process_ticket(batch_new, SCHEMA_PATH, logger,
                               Path(INBOX_ROOT) / 'inbox.batch')
    
    batch_cur = os.path.join(INBOX_ROOT, 'inbox.batch', 'cur', "TICK-9621916A.json")
    test_log.test("End-to-end: batch ticket processed",
                  os.path.exists(batch_cur),
                  f"cur exists: {os.path.exists(batch_cur)}")
    
    # Summary of files
    test_log.info("Final state:")
    for queue in ['inbox', 'inbox.urgent', 'inbox.batch']:
        for subdir in ['new', 'cur', 'quarantine']:
            dir_path = os.path.join(INBOX_ROOT, queue, subdir)
            if os.path.exists(dir_path):
                files = os.listdir(dir_path)
                test_log.info(f"  {queue}/{subdir}/: {len(files)} file(s)")
    
    test_log.phase_end("End-to-End Pipeline")
    test_log.write_results()
    
    return test_log.results['failed'] == 0


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='SecuraTron Stagecraft Inbox — Gated Validation Test Suite'
    )
    parser.add_argument('--phase', type=int, choices=[0, 1, 2, 3, 4, 5],
                        help='Run only the specified phase (0-5)')
    parser.add_argument('--all', action='store_true', dest='all_phases',
                        help='Run all phases')
    parser.add_argument('--verbose', action='store_true',
                        help='Verbose output')
    
    args = parser.parse_args()
    
    # Determine which phases to run
    if args.phase is not None:
        phases = [args.phase]
    elif args.all_phases:
        phases = [0, 1, 2, 3, 4, 5]
    else:
        # Default: run all phases
        phases = [0, 1, 2, 3, 4, 5]
    
    print("=" * 60)
    print("SecuraTron Stagecraft Inbox — Gated Validation Tests")
    print("=" * 60)
    print(f"Inbox root: {INBOX_ROOT}")
    print(f"Schema path: {SCHEMA_PATH}")
    print(f"Phases to run: {phases}")
    print("=" * 60)
    
    overall_passed = True
    
    # Run each phase
    phase_funcs = {
        0: phase_0_schema_integrity,
        1: phase_1_directory_structure,
        2: phase_2_schema_validation,
        3: phase_3_ticket_generation,
        4: phase_4_watcher_integration,
        5: phase_5_end_to_end,
    }
    
    phase_names = {
        0: "Schema File Integrity",
        1: "Directory Structure",
        2: "Schema Validation",
        3: "Ticket Generation",
        4: "Watcher Integration",
        5: "End-to-End Pipeline",
    }
    
    for phase in phases:
        test_log = TestLogger(LOG_DIR, f"phase-{phase:02d}")
        try:
            result = phase_funcs[phase](test_log)
            if not result:
                overall_passed = False
        except Exception as e:
            test_log.error(f"Phase {phase} crashed: {e}")
            test_log.phase_end(phase_names[phase], 'crash')
            test_log.write_results()
            overall_passed = False
    
    # Summary
    print("=" * 60)
    if overall_passed:
        print("ALL PHASES PASSED")
    else:
        print("ONE OR MORE PHASES FAILED")
    print(f"Log directory: {LOG_DIR}")
    print("=" * 60)
    
    sys.exit(0 if overall_passed else 1)


if __name__ == '__main__':
    main()
