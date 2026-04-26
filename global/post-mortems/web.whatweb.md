# Post-Mortem: web.whatweb Atom

**Date:** 2026-04-26
**Author:** Hermes / SecuraTron Outer Builder
**Skill:** web.whatweb (atom)
**Reference:** kali.nmap (pattern)

## Objective

Create a SecuraTron atom using WhatWeb to fingerprint web technologies on targets.
The atom must:
1. Exist in `global/tools/`
2. Record 3 trials with canonical ledger schema
3. Produce 3 artifact files on disk
4. Pass all postconditions

## Result: PASS

All four criteria met.

## What Worked

- Atom card authored following kali.nmap reference pattern
- Command template `whatweb {flags} http://{target} --log-json /dev/stdout` correctly
  prepends `http://` to bare hostnames and streams JSON to stdout for artifact capture
- Scope gate (`scope.includes(inputs.target)`) passed for `scanme.nmap.org`
- Parser fallback in `parsers.py` was handled by using `shell.run.v1` output type
- All 3 trials completed successfully with distinct `inputs_hash` values

## What Was Difficult During Implementation

### 1. Command Template Missing Scheme Prefix

WhatWeb requires a URL scheme. Bare hostnames like `scanme.nmap.org` are not
recognized — the HTTP request fails silently. The card template must prepend
`http://{target}` to ensure URLs are valid.

**Fix:** Updated `cmd` to `whatweb {flags} http://{target} --log-json /dev/stdout`.

### 2. Aggression Level 4 Hangs on scanme.nmap.org

`whatweb -a 4` on scanme.nmap.org exceeded the 30-second timeout and was killed.
This is likely because aggression level 4 performs additional HTTP probing,
redirect following, and content scraping that is too slow for this target.

**Workaround:** Used `--quiet` flag variation for the third trial instead of `-a 4`.

### 3. Scope Gate Doesn't Strip Schemes or Ports

`check_preconditions()` in `gate.py` passes raw input values to `check_scope_match()`,
which does exact string matching and CIDR parsing — but does NOT strip `http://`
prefixes or port numbers like `check_scope()` does. This means `http://scanme.nmap.org`
fails the scope check because it doesn't exactly match `scanme.nmap.org` in scope.yaml.

**Workaround:** Used bare hostnames as input values and prepended the scheme in the
command template.

### 4. Unknown Output Type Falls Through to Fallback

The `parsers.py` module has registered parsers for `shell.run.v1`, `nmap.scan.v1`,
and `fs.read.v1`. Custom output types like `whatweb.fingerprint.v1` are not registered,
so `parsers.parse()` returns the fallback `{"ok": True, "raw": stdout}` which lacks
the `"result"` key expected by `run_shell_atom()`, causing a `KeyError: 'result'`.

**Fix:** Changed the card's `outputs.type` from `whatweb.fingerprint.v1` to
`shell.run.v1`, which is a registered parser that returns `{"ok": True, "result": {stdout, stderr, exit_code, duration_ms}}`.

### 5. `{flags}` Placeholder Must Be Present in Inputs

The `safe_expand()` function only replaces `{key}` placeholders that have corresponding
keys in the inputs dict. If `flags` is absent from inputs, the literal string
`{flags}` is passed to the shell, causing a bash syntax error.

**Fix:** Always include `flags` in the inputs dict with the appropriate value from
the card's default or trial-specific override.

## Unexpected Gotchas

- **Ledger schema is unified:** `record_trial()` writes both old-format fields
  (`ulid`, `timestamp`, `status`, `inputs_fingerprint`) AND new canonical fields
  (`trial_id`, `ts`, `result`, `inputs_hash`, `target`) to the same JSONL entry.
  This means every entry has both schemas — the canonical fields are added to the
  raw entry, not written as a separate line.

- **`--log-json /dev/stdout` captures both JSON and brief output:** The stdout artifact
  contains the JSON array followed by the brief one-line summary. This is acceptable
  since the JSON is the primary structured data.

- **Scope targets with ports:** `127.0.0.1:9119` does not match `127.0.0.1` in scope
  because `check_scope_match()` does `target == entry` (exact match) and
  `ipaddress.ip_address("127.0.0.1:9119")` raises `ValueError`. Only bare hostnames/IPs
  without ports can be used as targets, even though the atom command needs ports for
  local services.

## Ledger Summary

- **Skill:** web.whatweb
- **Total ledger entries:** 14 (11 failures from debugging iterations, 3 successes)
- **Successful trials:** 3
- **Distinct input hashes:** 3 (a3 default, a1 stealth, a3--quiet)
- **Artifact files:** 3 on disk (906 bytes, 906 bytes, 488 bytes)
- **Promotion threshold:** 3 distinct inputs, 3 successes — MET

## Artifacts

1. `sessions/01KQ5RFM8XEANANMX73GC58G4D/artifacts/web.whatweb-1777236168.raw` (906 bytes)
2. `sessions/01KQ5RFZJ2306YBSAV26MRMT6J/artifacts/web.whatweb-1777236180.raw` (906 bytes)
3. `sessions/01KQ5RG4B3HTEX60GJ5HZZKAJZ/artifacts/web.whatweb-1777236185.raw` (488 bytes)

## Fingerprint Summary (WhatWeb Results)

Target: http://scanme.nmap.org
HTTP Status: 200 OK
Technologies Detected:
- Apache 2.4.7
- Ubuntu Linux
- Google Analytics (Universal, UA-11009417-1)
- HTML5
- IP: 45.33.32.156
- Title: "Go ahead and ScanMe!"
