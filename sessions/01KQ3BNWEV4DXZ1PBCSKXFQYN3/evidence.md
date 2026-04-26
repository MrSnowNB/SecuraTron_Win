# Evidence: T-CODEX-LEMONADE-WIRING-001-A

## Step 2: Probe
- BASE: http://localhost:13305/api/v1
- Result: HTTP 200

## Step 3: Model List
- Qwen3.6-27B-GGUF
- Qwen3.6-35B-A3B-GGUF

## Step 4: Smoke Test
- Status: SUCCESS (after increasing context to 131072)

## Config: ~/.codex/config.toml
# Securatron / Codex CLI config
# Routes all traffic through local Lemonade Server (AMD Strix Halo, Qwen3.6)
# Written by T-CODEX-LEMONADE-WIRING-001

model = "Qwen3.6-27B-GGUF"
model_provider = "lemonade"

approval_policy = "on-request"
sandbox_mode = "workspace-write"

[model_providers.lemonade]
name = "Lemonade (local, AMD Strix Halo)"
base_url = "http://localhost:13305/api/v1"
wire_api = "chat"
env_key = "LEMONADE_API_KEY"
stream_idle_timeout_ms = 600000

[profiles.lemonade-27b]
model_provider = "lemonade"
model = "Qwen3.6-27B-GGUF"

[profiles.lemonade-35b-a3b]
model_provider = "lemonade"
model = "Qwen3.6-35B-A3B-GGUF"

[projects."/home/mark/.securatron"]
trust_level = "trusted"

## Step 9: Live Round-Trip
- Version: 0.72.0
- Output: HARNESS_ONLINE

## Step 10: Tool-Use Validation
- Result: Qwen3.6-27B emitted valid structured 'cat' tool call.

## Red-Light Stops
- 0.125.0 Incompatibility: Downgraded to 0.72.0 to restore 'wire_api = chat' support.
