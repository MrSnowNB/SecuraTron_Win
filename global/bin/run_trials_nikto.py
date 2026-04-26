#!/usr/bin/env python3
"""Run three web.nikto trials via dispatch."""
import sys, os, yaml, time, json
from pathlib import Path
from ulid import ULID

sys.path.insert(0, '/home/mark/.securatron/global/bin')
import dispatch as dp
import gate
import ledger

# Load the card
card_path = '/home/mark/.securatron/global/tools/web.nikto.yaml'
with open(card_path) as f:
    card = yaml.safe_load(f)

print(f'=== LOADED CARD: {card["id"]} ===')
print(f'  Cmd: {card["implementation"]["cmd"]}')
print(f'  Output type: {card["outputs"]["type"]}')
print(f'  Artifact path: {card["outputs"]["artifact_path"]}')
print()

# 3 trials with distinct flags for distinct inputs_hash
flags_map = {
    0: '-Tuning 23b',         # Misconfig + Info Disclosure + Software ID
    1: '',                     # Full default scan (maxtime 30s caps it)
    2: '-Tuning 23b -port 80,443',  # Specific ports
}

targets = [
    ('scanme.nmap.org', f'Trial 1: tuned scan (flag=0)'),
    ('scanme.nmap.org', f'Trial 2: full scan (flag=1)'),
    ('scanme.nmap.org', f'Trial 3: multi-port (flag=2)'),
]

results = []
for i, (target, label) in enumerate(targets):
    session_id = str(ULID())
    print(f'--- {label} ---')
    print(f'  Target: {target}')
    print(f'  Session: {session_id}')
    
    flags = flags_map[i]
    inputs = {
        'target': target,
        'flags': flags,
        'session': session_id,
        'ts': str(int(time.time())),
    }
    
    # Pre-flight: check preconditions
    pre_passed, pre_failures = gate.check_preconditions(
        card, inputs,
        scope_file='/home/mark/.securatron/projects/lab-internal/scope.yaml'
    )
    print(f'  Flags: "{flags}"')
    print(f'  Preconditions: passed={pre_passed}, failures={pre_failures}')
    
    if not pre_passed:
        print(f'  SKIPPING — gate refused: {pre_failures}')
        results.append({
            'label': label, 'target': target, 'session_id': session_id,
            'inputs': inputs, 'ok': False, 'reason': f'gate_refused: {pre_failures}',
            'artifact_exists': False, 'artifact_size': 0,
        })
        print()
        continue
    
    # Run dispatch
    result = dp.dispatch(card, inputs, 'lab-internal', session_id)
    print(f'  Dispatch result: ok={result.get("ok")}, reason={result.get("reason", "N/A")}')
    
    # Check artifact
    artifact_rel = result.get('artifact_path', '')
    exists = False
    size = 0
    if artifact_rel:
        artifact_path = Path('/home/mark/.securatron') / artifact_rel
        exists = artifact_path.exists() and artifact_path.is_file()
        size = artifact_path.stat().st_size if exists else 0
        print(f'  Artifact: path={artifact_rel}')
        print(f'  Artifact (dispatch raw): exists={exists}, size={size} bytes')
    
    # Also check for nikto JSON file (nikto appends .json extension)
    nikto_json_path = Path(f'/home/mark/.securatron/sessions/{session_id}/artifacts/nikto-{inputs["ts"]}.json.json')
    if not nikto_json_path.exists():
        # Also try without .json append (if format was derived from extension)
        nikto_json_path = Path(f'/home/mark/.securatron/sessions/{session_id}/artifacts/nikto-{inputs["ts"]}.json')
    
    if nikto_json_path.exists():
        nikto_size = nikto_json_path.stat().st_size
        print(f'  Artifact (nikto json): exists=True, size={nikto_size} bytes')
        content = nikto_json_path.read_text()[:500]
        print(f'  Nikto JSON preview:')
        for line in content.strip().split('\n')[:10]:
            print(f'    {line}')
        # Validate JSON
        try:
            parsed = json.loads(content.strip())
            print(f'  JSON valid: True, top-level type: {type(parsed).__name__}')
            if isinstance(parsed, list) and len(parsed) > 0:
                v = parsed[0].get('vulnerabilities', [])
                print(f'  Vulnerabilities found: {len(v)}')
        except json.JSONDecodeError as e:
            print(f'  JSON valid: False — {e}')
        exists = True
        size = nikto_size
    else:
        print(f'  Artifact (nikto json): not found')
    
    results.append({
        'label': label, 'target': target, 'session_id': session_id,
        'inputs': inputs, 'ok': result.get('ok', False),
        'reason': result.get('reason', 'unknown'),
        'artifact_exists': exists, 'artifact_size': size,
    })
    print()

# Print summary
print('=== TRIAL SUMMARY ===')
all_pass = True
for r in results:
    status = 'PASS' if r['ok'] and r['artifact_exists'] and r['artifact_size'] > 0 else 'FAIL'
    print(f'  {r["label"]}: {status}')
    if not r['ok'] or not r['artifact_exists'] or r['artifact_size'] == 0:
        all_pass = False
        if not r['ok']:
            print(f'    Dispatch reason: {r["reason"]}')
        if not r['artifact_exists']:
            print(f'    Artifact not found on disk')

print()
print('=== LEDGER CHECK ===')
ledger_path = Path('/home/mark/.securatron/global/ledger/web.nikto.trials.jsonl')
if ledger_path.exists():
    entries = []
    with open(ledger_path) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line.strip()))
    print(f'  Total entries: {len(entries)}')
    successes = [e for e in entries if e.get('result') == 'success']
    print(f'  Successful: {len(successes)}')
    if successes:
        for s in successes:
            h = s.get('inputs_hash', 'N/A')
            t = s.get('target', 'N/A')
            sid = s.get('session_id', 'N/A')
            print(f'    trial_id={s.get("trial_id","?")} target={t} hash={h[:16]}... session={sid}')
else:
    print('  Ledger file not found')

sys.exit(0 if all_pass else 1)
