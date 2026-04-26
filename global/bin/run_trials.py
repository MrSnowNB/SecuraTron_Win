#!/usr/bin/env python3
"""Run three web.whatweb trials via dispatch."""
import sys, os, yaml, subprocess, time, json
from pathlib import Path
from ulid import ULID

sys.path.insert(0, '/home/mark/.securatron/global/bin')
import dispatch as dp
import gate
import ledger

# Load the card
card_path = '/home/mark/.securatron/global/tools/web.whatweb.yaml'
with open(card_path) as f:
    card = yaml.safe_load(f)

print(f'=== LOADED CARD: {card["id"]} ===')
print()

targets = [
    ('scanme.nmap.org', 'Trial 1: scanme.nmap.org (aggression 3 default)'),
    ('scanme.nmap.org', 'Trial 2: scanme.nmap.org (aggression 1 stealth)'),
    ('scanme.nmap.org', 'Trial 3: scanme.nmap.org (aggression 4 heavy)'),
]

results = []
for i, (target, label) in enumerate(targets):
    session_id = str(ULID())
    print(f'--- {label} ---')
    print(f'  Target: {target}')
    print(f'  Session: {session_id}')
    
    # Vary flags for distinct input hashes
    # a4 hangs on scanme.nmap.org, so we use other flag variations
    flags_map = {0: '-a 3', 1: '-a 1', 2: '-a 3 --quiet'}
    flags = flags_map[i]
    inputs = {'target': target, 'flags': flags}
    
    # Pre-flight: check preconditions
    pre_passed, pre_failures = gate.check_preconditions(
        card, inputs, 
        scope_file='/home/mark/.securatron/projects/lab-internal/scope.yaml'
    )
    print(f'  Flags: {flags}')
    print(f'  Preconditions: passed={pre_passed}, failures={pre_failures}')
    
    # Run dispatch
    result = dp.dispatch(card, inputs, 'lab-internal', session_id)
    print(f'  Dispatch result: ok={result.get("ok")}, reason={result.get("reason", "N/A")}')
    
    # Check artifact
    artifact_rel = result.get('artifact_path', '')
    if artifact_rel:
        artifact_path = Path('/home/mark/.securatron') / artifact_rel
        exists = artifact_path.exists() and artifact_path.is_file()
        size = artifact_path.stat().st_size if exists else 0
        if exists and size > 0:
            content = artifact_path.read_text()[:300]
            print(f'  Artifact preview (300 chars):')
            print(f'    {content[:250]}...')
        else:
            print(f'  Artifact: path={artifact_rel}, exists={exists}, size={size}')
    else:
        exists = False
        size = 0
        print(f'  Artifact: no path returned')
    
    results.append({
        'label': label,
        'target': target,
        'session_id': session_id,
        'inputs': inputs,
        'ok': result.get('ok', False),
        'reason': result.get('reason', 'unknown'),
        'artifact_exists': exists,
        'artifact_size': size,
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

sys.exit(0 if all_pass else 1)
