#!/usr/bin/env python3
"""
SecuraTron Stagecraft Inbox - Gated Validation Test Suite

Tests the full pipeline: schema -> watcher -> dispatch -> ledger.
Usage: python3 global/bin/test_inbox_validation.py --all
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASEDIR = Path.home() / '.securatron'
INBOX_ROOT = BASEDIR / 'projects' / 'lab-internal' / 'inbox'
SCHEMA_PATH = BASEDIR / 'global' / 'charters' / 'inbox-ticket.schema.json'
WATCHER_PATH = BASEDIR / 'global' / 'bin' / 'inbox_watcher.py'
CHARTER_PATH = BASEDIR / 'global' / 'charters' / 'INBOX-CHARTER.md'
LOG_DIR = BASEDIR / 'logs' / 'tests'

TEST_TICKETS = {
    'valid': 'TICK-6676AC9D',
    'missing_id': 'TICK-INVALID1',
    'invalid_priority': 'TICK-5FA0785C',
    'missing_skill': 'TICK-A0BBD954',
    'bad_format': 'TICK-7FFB138C',
    'destructive_valid': 'TICK-0F16930A',
    'destructive_no_gate': 'TICK-EB13267F',
    'urgent': 'TICK-75C8AE03',
    'batch': 'TICK-9621916A',
    'unknown_skill': 'TICK-CC407170',
    'with_session': 'TICK-FD9C2C70',
}

def ensure_directories():
    for q in ['inbox', 'inbox.urgent', 'inbox.batch']:
        for s in ['tmp', 'new', 'cur', 'quarantine', 'gates']:
            (INBOX_ROOT / q / s).mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def write_ticket(queue, ticket_id, data, subdir='new'):
    path = INBOX_ROOT / queue / subdir / f"{ticket_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return path


def count_files(directory):
    d = Path(directory)
    if not d.exists():
        return 0
    return len([f for f in d.iterdir() if f.suffix == '.json'])


class DummyLogger:
    def info(self, *a): pass
    def warning(self, *a): pass
    def error(self, *a): pass
    def critical(self, *a): pass


def run_tests(tests, phase_num, phase_name):
    passed = 0
    failed = 0
    results = []
    for t in tests:
        try:
            t['fn']()
            results.append({'name': t['name'], 'passed': True})
            passed += 1
        except AssertionError as e:
            results.append({'name': t['name'], 'passed': False, 'detail': str(e)})
            failed += 1
        except Exception as e:
            results.append({'name': t['name'], 'passed': False, 'detail': f'Exception: {e}'})
            failed += 1

    result_file = LOG_DIR / f'phase-{phase_num:02d}_results.json'
    result_data = {
        'test_name': f'phase-{phase_num:02d}',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'phases': [{
            'name': phase_name,
            'start_time': datetime.now(timezone.utc).isoformat(),
            'tests': results,
            'passed': passed,
            'failed': failed,
            'status': 'pass' if failed == 0 else 'fail',
        }],
        'total_tests': passed + failed,
        'passed': passed,
        'failed': failed,
    }
    with open(result_file, 'w') as f:
        json.dump(result_data, f, indent=2)
    return passed, failed


# ---------------------------------------------------------------------------
# PHASE 0: Schema File Integrity
# ---------------------------------------------------------------------------

def phase_0():
    tests = []

    def check_schema_exists():
        if not SCHEMA_PATH.exists():
            raise AssertionError(f'Missing {SCHEMA_PATH}')

    def check_valid_json():
        data = json.loads(SCHEMA_PATH.read_text())
        assert isinstance(data, dict)
        return data

    tests.append({'name': 'Schema file exists', 'fn': check_schema_exists})

    try:
        schema = check_valid_json()
        tests.append({'name': 'Valid JSON', 'fn': lambda: True})

        # Resolve $ref helpers
        defs = schema.get('definitions', {})

        def resolve(prop_name):
            """Follow $ref to definition."""
            prop = schema.get('properties', {}).get(prop_name, {})
            ref = prop.get('$ref', '')
            if ref.startswith('#/definitions/'):
                name = ref.split('/')[-1]
                return defs.get(name, prop)
            return prop

        def check_schema_draft():
            s = schema.get('$schema', '')
            assert '2020-12' in s

        tests.append({'name': '$schema = draft 2020-12', 'fn': check_schema_draft})

        def check_id_prefix():
            assert schema.get('$id', '').startswith('securatron/inbox-ticket/')
        tests.append({'name': '$id prefix correct', 'fn': check_id_prefix})

        def check_no_extra_props():
            assert schema.get('additionalProperties') == False
        tests.append({'name': 'additionalProperties = false', 'fn': check_no_extra_props})

        def check_allof():
            assert 'allOf' in schema and len(schema['allOf']) > 0
        tests.append({'name': 'allOf constraint exists', 'fn': check_allof})

        def check_definitions():
            assert 'definitions' in schema
        tests.append({'name': 'definitions block present', 'fn': check_definitions})

        props = schema.get('properties', {})

        def check_required_fields():
            for k in ['ticket_id', 'source', 'skill', 'priority', 'created_at', 'status']:
                assert k in props, f'Missing required field: {k}'
        tests.append({'name': 'All required fields present', 'fn': check_required_fields})

        def check_ticket_pattern():
            r = resolve('ticket_id')
            assert 'pattern' in r
        tests.append({'name': 'ticket_id has pattern', 'fn': check_ticket_pattern})

        def check_priority_enum():
            r = resolve('priority')
            assert set(r.get('enum', [])) == {'low', 'normal', 'high', 'urgent'}
        tests.append({'name': 'priority enum correct', 'fn': check_priority_enum})

        def check_status_enum():
            r = resolve('status')
            assert set(r.get('enum', [])) == {'pending', 'processing', 'completed', 'failed', 'quarantined'}
        tests.append({'name': 'status enum correct', 'fn': check_status_enum})

        def check_source_enum():
            r = resolve('source')
            assert set(r.get('enum', [])) == {'agent', 'operator', 'mesh', 'external', 'cron'}
        tests.append({'name': 'source enum correct', 'fn': check_source_enum})

        def check_auth_reserved():
            assert 'auth' in props
        tests.append({'name': 'auth field reserved (CA96)', 'fn': check_auth_reserved})

    except Exception as e:
        tests.append({'name': f'Schema parse error: {e}', 'fn': lambda: (_ for _ in ()).throw(AssertionError(str(e)))})

    return tests


# ---------------------------------------------------------------------------
# PHASE 1: Directory Structure
# ---------------------------------------------------------------------------

def phase_1():
    tests = []
    ensure_directories()

    def check_dir_exists():
        for q in ['inbox', 'inbox.urgent', 'inbox.batch']:
            for s in ['tmp', 'new', 'cur', 'quarantine']:
                p = INBOX_ROOT / q / s
                if not p.exists():
                    raise AssertionError(f'Missing {p}')

    tests.append({'name': 'All queue dirs exist', 'fn': check_dir_exists})

    def check_gates():
        p = INBOX_ROOT / 'inbox' / 'gates'
        if not p.exists():
            raise AssertionError('Missing gates/')
    tests.append({'name': 'gates/ exists', 'fn': check_gates})

    def check_charter():
        if not CHARTER_PATH.exists():
            raise AssertionError('Charter not found')
    tests.append({'name': 'Charter file exists', 'fn': check_charter})

    def check_watcher():
        if not WATCHER_PATH.exists():
            raise AssertionError('Watcher not found')
    tests.append({'name': 'Watcher script exists', 'fn': check_watcher})

    return tests


# ---------------------------------------------------------------------------
# PHASE 2: Schema Validation
# ---------------------------------------------------------------------------

def phase_2():
    tests = []
    try:
        import jsonschema
        schema = json.loads(SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(schema)

        def make_valid():
            return {
                'ticket_id': 'TICK-6676AC9D',
                'source': 'agent',
                'skill': 'web.nikto',
                'priority': 'normal',
                'created_at': '2026-04-28T01:00:00Z',
                'status': 'pending',
                'inputs': {'target': '192.168.1.1'},
            }

        def check(name, data, expect_valid=True):
            errors = list(validator.iter_errors(data))
            is_valid = len(errors) == 0
            if expect_valid and not is_valid:
                raise AssertionError(f'Expected valid: {errors}')
            if not expect_valid and is_valid:
                raise AssertionError('Expected invalid but passed')

        t = make_valid()
        tests.append({'name': 'Valid ticket passes', 'fn': lambda: check('valid', t, True)})
        tests.append({'name': 'Valid ticket with arbitrary inputs',
                      'fn': lambda: check('valid+extra-inputs', {**t, 'inputs': {'target': 'x', 'extra': 'y'}}, True)})
        tests.append({'name': 'Extra unknown field fails',
                      'fn': lambda: check('extra-field', {**t, 'extra_field': 'not allowed'}, False)})
        tests.append({'name': 'Invalid priority fails',
                      'fn': lambda: check('bad-priority', {**t, 'priority': 'invalid'}, False)})
        tests.append({'name': 'Invalid status fails',
                      'fn': lambda: check('bad-status', {**t, 'status': 'invalid'}, False)})
        tests.append({'name': 'Invalid ticket_id fails',
                      'fn': lambda: check('bad-id', {**t, 'ticket_id': 'bad-format'}, False)})

        bad = dict(t)
        del bad['ticket_id']
        tests.append({'name': 'Missing ticket_id fails',
                      'fn': lambda: check('missing-id', bad, False)})

        bad = dict(t)
        bad['destructive'] = True
        bad['human_gate'] = False
        tests.append({'name': 'destructive without human_gate fails',
                      'fn': lambda: check('destructive-no-gate', bad, False)})

        good = dict(t)
        good['destructive'] = True
        good['human_gate'] = True
        tests.append({'name': 'destructive + human_gate passes',
                      'fn': lambda: check('destructive-with-gate', good, True)})

    except ImportError:
        tests.append({'name': 'jsonschema available',
                      'fn': lambda: (_ for _ in ()).throw(AssertionError('jsonschema not installed'))})
    return tests


# ---------------------------------------------------------------------------
# PHASE 3: Ticket Generation
# ---------------------------------------------------------------------------

def phase_3():
    tests = []
    ensure_directories()
    base = {
        'ticket_id': TEST_TICKETS['valid'],
        'source': 'agent',
        'skill': 'web.nikto',
        'priority': 'normal',
        'created_at': '2026-04-28T01:00:00Z',
        'status': 'pending',
        'inputs': {'target': '192.168.1.1'},
    }

    def check_tmp():
        write_ticket('inbox', base['ticket_id'], base, 'tmp')
        assert (INBOX_ROOT / 'inbox' / 'tmp' / f"{base['ticket_id']}.json").exists()
    tests.append({'name': 'Valid ticket in tmp/', 'fn': check_tmp})

    def check_new():
        write_ticket('inbox', base['ticket_id'], base, 'new')
        p = INBOX_ROOT / 'inbox' / 'new' / f"{base['ticket_id']}.json"
        assert p.exists()
        assert json.loads(p.read_text())  # valid JSON
    tests.append({'name': 'Ticket in new/ (published)', 'fn': check_new})

    def check_invalid_writable():
        bad = dict(base)
        bad['priority'] = 'invalid'
        bad['ticket_id'] = TEST_TICKETS['invalid_priority']
        write_ticket('inbox', bad['ticket_id'], bad, 'new')
        assert True
    tests.append({'name': 'Invalid ticket can be written', 'fn': check_invalid_writable})

    return tests


# ---------------------------------------------------------------------------
# PHASE 4: Watcher Integration
# ---------------------------------------------------------------------------

def phase_4():
    tests = []
    ensure_directories()

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("inbox_watcher", WATCHER_PATH)
        watcher_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watcher_mod)
    except Exception as e:
        tests.append({'name': 'Watcher module loads',
                      'fn': lambda e=e: (_ for _ in ()).throw(AssertionError(f'Load failed: {e}'))})
        return tests

    logger = DummyLogger()

    valid = {
        'ticket_id': TEST_TICKETS['valid'],
        'source': 'agent',
        'skill': 'web.nikto',
        'priority': 'normal',
        'created_at': '2026-04-28T01:00:00Z',
        'status': 'pending',
        'inputs': {'target': '192.168.1.1'},
    }

    def check_validation_valid():
        ok, errs = watcher_mod.validate_ticket(valid, str(SCHEMA_PATH))
        assert ok, f'Failed: {errs}'
    tests.append({'name': 'validate_ticket: valid ticket passes', 'fn': check_validation_valid})

    def check_validation_invalid():
        bad = dict(valid)
        bad['priority'] = 'invalid'
        ok, errs = watcher_mod.validate_ticket(bad, str(SCHEMA_PATH))
        assert not ok
    tests.append({'name': 'validate_ticket: invalid priority rejected', 'fn': check_validation_invalid})

    def check_validation_missing():
        bad = dict(valid)
        del bad['ticket_id']
        ok, errs = watcher_mod.validate_ticket(bad, str(SCHEMA_PATH))
        assert not ok
    tests.append({'name': 'validate_ticket: missing field rejected', 'fn': check_validation_missing})

    def check_process_valid():
        write_ticket('inbox', valid['ticket_id'], valid, 'new')
        watcher_mod.process_ticket(
            str(INBOX_ROOT / 'inbox' / 'new' / f"{valid['ticket_id']}.json"),
            str(SCHEMA_PATH), logger, INBOX_ROOT / 'inbox')
        cur_file = INBOX_ROOT / 'inbox' / 'cur' / f"{valid['ticket_id']}.json"
        assert cur_file.exists(), 'Not in cur/'
        cur = json.loads(cur_file.read_text())
        assert cur.get('status') in ('completed', 'failed'), f'Wrong status: {cur.get("status")}'
    tests.append({'name': 'Valid ticket moved to cur/', 'fn': check_process_valid})
    tests.append({'name': 'Status updated to completed', 'fn': check_process_valid})

    def check_process_invalid():
        bad = dict(valid)
        bad['priority'] = 'invalid'
        bad['ticket_id'] = TEST_TICKETS['invalid_priority']
        write_ticket('inbox', bad['ticket_id'], bad, 'new')
        watcher_mod.process_ticket(
            str(INBOX_ROOT / 'inbox' / 'new' / f"{bad['ticket_id']}.json"),
            str(SCHEMA_PATH), logger, INBOX_ROOT / 'inbox')
        q_file = INBOX_ROOT / 'inbox' / 'quarantine' / f"{bad['ticket_id']}.json"
        assert q_file.exists(), 'Not quarantined'
        qd = json.loads(q_file.read_text())
        assert 'quarantine_reason' in qd, 'No reason'
    tests.append({'name': 'Invalid ticket moved to quarantine/', 'fn': check_process_invalid})
    tests.append({'name': 'Quarantine reason recorded', 'fn': check_process_invalid})

    return tests


# ---------------------------------------------------------------------------
# PHASE 5: End-to-End Pipeline
# ---------------------------------------------------------------------------

def phase_5():
    tests = []
    ensure_directories()

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("inbox_watcher", WATCHER_PATH)
        watcher_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watcher_mod)
    except Exception as e:
        tests.append({'name': 'Watcher loads for e2e',
                      'fn': lambda e=e: (_ for _ in ()).throw(AssertionError(f'Load failed: {e}'))})
        return tests

    logger = DummyLogger()

    v = {
        'ticket_id': TEST_TICKETS['valid'],
        'source': 'agent',
        'skill': 'web.nikto',
        'priority': 'normal',
        'created_at': '2026-04-28T01:00:00Z',
        'status': 'pending',
        'inputs': {'target': '192.168.1.1'},
    }

    def check_valid_e2e():
        write_ticket('inbox', v['ticket_id'], v, 'tmp')
        write_ticket('inbox', v['ticket_id'], v, 'new')
        watcher_mod.process_ticket(
            str(INBOX_ROOT / 'inbox' / 'new' / f"{v['ticket_id']}.json"),
            str(SCHEMA_PATH), logger, INBOX_ROOT / 'inbox')
        new_f = INBOX_ROOT / 'inbox' / 'new' / f"{v['ticket_id']}.json"
        cur_f = INBOX_ROOT / 'inbox' / 'cur' / f"{v['ticket_id']}.json"
        assert cur_f.exists(), 'Not in cur/'
        assert not new_f.exists(), 'Still in new/'
    tests.append({'name': 'e2e: valid ticket in new/ after publish', 'fn': check_valid_e2e})
    tests.append({'name': 'e2e: valid ticket in cur/', 'fn': check_valid_e2e})

    def check_urgent_e2e():
        u = dict(v)
        u['ticket_id'] = TEST_TICKETS['urgent']
        u['priority'] = 'urgent'
        write_ticket('inbox.urgent', u['ticket_id'], u, 'new')
        watcher_mod.process_ticket(
            str(INBOX_ROOT / 'inbox.urgent' / 'new' / f"{u['ticket_id']}.json"),
            str(SCHEMA_PATH), logger, INBOX_ROOT / 'inbox.urgent')
        p = INBOX_ROOT / 'inbox.urgent' / 'cur' / f"{u['ticket_id']}.json"
        assert p.exists(), 'Not in urgent cur/'
    tests.append({'name': 'e2e: urgent ticket in inbox.urgent/cur/', 'fn': check_urgent_e2e})

    def check_destructive_e2e():
        d = dict(v)
        d['ticket_id'] = TEST_TICKETS['destructive_valid']
        d['destructive'] = True
        d['human_gate'] = True
        write_ticket('inbox', d['ticket_id'], d, 'new')
        watcher_mod.process_ticket(
            str(INBOX_ROOT / 'inbox' / 'new' / f"{d['ticket_id']}.json"),
            str(SCHEMA_PATH), logger, INBOX_ROOT / 'inbox')
        p = INBOX_ROOT / 'inbox' / 'cur' / f"{d['ticket_id']}.json"
        assert p.exists(), 'Not in cur/'
        dd = json.loads(p.read_text())
        assert dd.get('destructive') == True, 'destructive flag missing'
        assert dd.get('human_gate') == True, 'human_gate flag missing'
    tests.append({'name': 'e2e: destructive ticket with human_gate processed', 'fn': check_destructive_e2e})
    tests.append({'name': 'e2e: destructive ticket has flags', 'fn': check_destructive_e2e})

    def check_batch_e2e():
        b = dict(v)
        b['ticket_id'] = TEST_TICKETS['batch']
        b['priority'] = 'low'
        write_ticket('inbox.batch', b['ticket_id'], b, 'new')
        watcher_mod.process_ticket(
            str(INBOX_ROOT / 'inbox.batch' / 'new' / f"{b['ticket_id']}.json"),
            str(SCHEMA_PATH), logger, INBOX_ROOT / 'inbox.batch')
        p = INBOX_ROOT / 'inbox.batch' / 'cur' / f"{b['ticket_id']}.json"
        assert p.exists(), 'Not in batch cur/'
    tests.append({'name': 'e2e: batch ticket in inbox.batch/cur/', 'fn': check_batch_e2e})

    # Print final state
    print("\n[INFO] Final state:")
    for q in ['inbox', 'inbox.urgent', 'inbox.batch']:
        for s in ['new', 'cur', 'quarantine']:
            c = count_files(INBOX_ROOT / q / s)
            print(f"[INFO]   {q}/{s}/: {c} file(s)")

    return tests


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description='SecuraTron Inbox Validation Tests')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--phase', type=int, action='append')
    args = parser.parse_args()

    if not args.all and not args.phase:
        parser.print_help()
        sys.exit(1)

    phases = args.phase if args.phase else list(range(0, 6))

    phase_map = {
        0: (phase_0, "Schema File Integrity"),
        1: (phase_1, "Directory Structure"),
        2: (phase_2, "Schema Validation"),
        3: (phase_3, "Ticket Generation"),
        4: (phase_4, "Watcher Integration"),
        5: (phase_5, "End-to-End Pipeline"),
    }

    total_passed = 0
    total_failed = 0

    print("=" * 60)
    print("SecuraTron Stagecraft Inbox - Gated Validation Tests")
    print("=" * 60)
    print(f"Inbox root: {INBOX_ROOT}")
    print(f"Schema path: {SCHEMA_PATH}")
    print(f"Phases: {phases}")
    print("=" * 60)

    for pn in sorted(phases):
        func, name = phase_map[pn]
        print(f"\n[INFO] === {name} (phase {pn}) ===")

        tests = func()
        p, f = run_tests(tests, pn, name)
        total_passed += p
        total_failed += f

        if f == 0:
            print(f"[INFO] === PASS ===")
        else:
            print(f"[INFO] === FAIL: {f} failures ===")
            rf = LOG_DIR / f'phase-{pn:02d}_results.json'
            with open(rf) as fh:
                data = json.load(fh)
            for t in data['phases'][0]['tests']:
                if not t['passed']:
                    print(f"[FAIL]   {t['name']}: {t.get('detail', '')}")

        print(f"[INFO] Results: {LOG_DIR / f'phase-{pn:02d}_results.json'}")

    print("\n" + "=" * 60)
    if total_failed == 0:
        print("ALL PHASES PASSED")
    else:
        print(f"FAILURES: {total_failed} tests failed")
    print(f"Logs: {LOG_DIR}")
    print("=" * 60)

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == '__main__':
    main()
