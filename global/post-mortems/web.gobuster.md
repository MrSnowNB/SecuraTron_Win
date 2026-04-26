Post-Mortem: web.gobuster Atom

Date: 2026-04-26
Author: Hermes / SecuraTron Outer Builder
Skill: web.gobuster (atom)
Reference: web.whatweb (pattern)

## Objective

Create a SecuraTron atom using Gobuster for web directory enumeration. The atom must:
1. Exist in global/tools/
2. Record 3 trials with canonical ledger schema
3. Produce 3 artifact files on disk
4. Have parameterized wordlist path (not hardcoded in command)
5. Pass all postconditions

## Result: PASS

All five criteria met.

## What Worked

- Atom card authored following web.whatweb reference pattern (closer than kali.nmap)
- Command template `gobuster dir -u http://{target} -w {wordlist} {flags}` correctly
  prepends `http://` to bare hostnames, streams text output to stdout
- Scope gate (scope.includes(inputs.target)) passed for scanme.nmap.org
- Parser fallback handled by using shell.run.v1 output type (no registered parser for gobuster)
- Wordlist path parameterized via {wordlist} input with sensible default
- All 3 trials completed successfully with distinct inputs_hash values
- 3 artifact files written, all non-empty with gobuster directory enumeration output

## What Was Difficult During Implementation

### 1. No CLI Entry Point on dispatch.py

The task description mentions `python3 ~/.securatron/global/bin/dispatch.py --skill web.gobuster`
but dispatch.py has no CLI entry point (no argparse, no sys.argv handling, no main()).
The dispatch function is invoked via run_trials.py scripts or via the MCP server
(mcp_server.py) which wraps dispatch in invoke_skill().

**Resolution:** Created run_trials_gobuster.py following the existing run_trials.py pattern
from the web.whatweb build.

### 2. No SecLists Wordlist Installed

The standard Kali SecLists package is not installed on this system. The gobuster wordlists
at /usr/share/seclists/Discovery/Web-Content/ do not exist.

**Resolution:** Used the distro-installed dirb wordlists at /usr/share/wordlists/dirb/small.txt
(959 lines). Also verified /usr/share/wordlists/dirb/common.txt (4614 lines) works but
takes ~30 seconds which is borderline the timeout. The /usr/share/wordlists/dirbuster/
directory also contains larger lists (87K+ lines) which would be far too slow.

### 3. Timeout Sensitivity with Larger Wordlists

common.txt (4614 lines) completes in ~30s on scanme.nmap.org — right at the edge of the
default timeout. Using extensions (-x) or more threads can push it over. small.txt (959 lines)
completes in ~6-12s which is comfortably within limits.

**Resolution:** Default to small.txt for speed reliability. Users who want deeper scans can
override the wordlist path with larger lists and increase flags.

### 4. Gobuster Output Contains Status Codes by Default

Without --no-error and -q flags, gobuster outputs a banner, progress indicator, and error
messages to stdout. This makes artifact parsing noisy.

**Resolution:** Include -f --no-error -q in default flags. -f appends / to paths (useful for
directory scanning), --no-error suppresses HTTP errors, -q suppresses the banner.

## Unexpected Gotchas

- **Gobuster appends / with -f:** Without -f, gobuster requests bare paths (e.g. /admin)
  which may return 404 even when the directory exists at /admin/. With -f, it requests
  /admin/ which is more reliable for directory enumeration.

- **Gobuster returns 403 for forbidden directories:** The default --status-codes
  blacklist is 404, meaning 403 responses ARE included in output. This means gobuster
  will report directories it can see but not access. This is actually desirable for
  reconnaissance (revealing hidden paths).

- **Artifact filename prefix:** The dispatch code uses {card['id']}-{ts} for artifact IDs,
  so the prefix is web.gobuster- not gobuster-. The glob pattern must account for this.

- **Expanded mode (-e) is faster:** Surprisingly, -e (expanded URLs) completed in 6.7s
  compared to 26.5s for the same flags without -e. The expanded output mode may use
  a different request batching strategy internally.

- **Gobuster -x extensions search adds depth:** With -x php,html,txt, gobuster appends
  each extension to every word in the wordlist, effectively tripling the request count.
  Despite this, it still completes in ~26s with small.txt because the target (scanme)
  has few matches.

## Ledger Summary

- Skill: web.gobuster
- Total ledger entries: 3 (all successful)
- Successful trials: 3
- Distinct input hashes: 3 (basic, with extensions, expanded URLs)
- Artifact files: 3 on disk (173 bytes, 173 bytes, 202 bytes)
- Promotion threshold: 3 distinct inputs, 3 successes — MET

## Artifacts

1. sessions/01KQ5V9NFG2W2RV2MMVB16P4BK/artifacts/web.gobuster-1777239119.raw (173 bytes)
2. sessions/01KQ5V9W3D8DHHP23KKXQGWJ46/artifacts/web.gobuster-1777239126.raw (173 bytes)
3. sessions/01KQ5VANA9GZRR96T2JZAMWZR4/artifacts/web.gobuster-1777239151.raw (202 bytes)

## Enumeration Summary (Gobuster Results on scanme.nmap.org)

### Trial 1 (basic, -f --no-error -q -t 10):
- icons/ (403)
- images/ (200)
- shared/ (403)

### Trial 2 (with extensions, -f --no-error -q -t 10 -x php,html,txt):
- icons/ (403)
- images/ (200)
- shared/ (403)
(Same results — scanme.nmap.org has no PHP/HTML/txt hidden files beyond the known dirs)

### Trial 3 (expanded, -f --no-error -q -t 10 -e):
- http://scanme.nmap.org/icons/ (403)
- http://scanme.nmap.org/images/ (200)
- http://scanme.nmap.org/shared/ (403)
(Same directories, full URLs instead of relative)

## Comparison with web.whatweb Post-Mortem Gotchas

| Gotcha | web.whatweb | web.gobuster | Status |
|--------|------------|--------------|--------|
| Scheme prefix | http://{target} in template | Same pattern | Avoided |
| Output parser | shell.run.v1 (no registered parser) | shell.run.v1 (same) | Consistent |
| Flags in inputs | Always include {flags} in inputs | Always include {flags} in inputs | Consistent |
| Scope gate | Bare hostnames only | Bare hostnames only | Consistent |
| Timeout | a4 hangs | common.txt ~30s borderline | Mitigated with small.txt |
| Wordlist path | N/A | Parameterized, not hardcoded | Added |
