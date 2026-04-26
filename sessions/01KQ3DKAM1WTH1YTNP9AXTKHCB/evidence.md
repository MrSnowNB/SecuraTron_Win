# Evidence: T-HERMES-LEMONADE-WIRING-001

## Step 2: Install
- Path C (GitHub script) SUCCESS.
- Version: Hermes Agent v0.11.0

## Step 4: Config
- Path: ~/.hermes/config.yaml
- Provider: custom (configured via model.default and custom_providers)

## Step 5: SOUL.md
- Identity established referencing Securatron memory tiers and doctrine.

## Step 6: Smoke Test
- Output: HERMES_ONLINE

## Step 7: Tool-Call Validation
- Result: SUCCESS. Summarized memory rules via file-read tool.

## Step 8: Side-by-Side Comparison
- Codex (66s): Fast, explicit tool logs, accurate but brief.
- Hermes (122s): Slower, context-rich, formatted, included risk metadata.

## Verdict
Hermes feels better for harness authorship because it naturally absorbs the SOUL.md and doctrine context, providing more comprehensive results.

## Invariants Check
- codex --version: 0.72.0 (Verified)
- config.toml: Unchanged (Verified)
