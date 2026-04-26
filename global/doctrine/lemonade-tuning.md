# Lemonade Tuning For Strix Halo + Qwen3.6-27B-GGUF

## Hardware Reality
- Host: HP Zbook, AMD Ryzen AI Max+ 395 (Strix Halo)
- Unified memory: 128 GB LPDDR5x-8000
- BIOS VRAM carve-out: 75 GB (verified via Lemonade telemetry)
- Available system RAM: ~53 GB
- iGPU: Radeon 8060S, Vulkan backend

## Configuration (~/.cache/lemonade/config.json)
```json
{
  "llamacpp": {
    "args": "-np 1 --ctx-size 131072 --keep 16"
  }
}
```

## Rationale
- `-np 1` — one slot, avoids per-slot 4k ctx cap that previously
  refused 47k-token Hermes prompts.
- `--ctx-size 131072` — full 128k context window.
- `--keep 16` — preserve system prompt across cache evictions.

## Verification (2026-04-26, task T-LEMONADE-SLOT-001)
- Smoke test: HARNESS_ONLINE returned via Codex.
- Tool-use validation: Qwen emitted structured `cat` tool call for memory-rules.md.
- Log confirmation: no further "4096 tokens exceeded" errors after restart.

## Known Trade-Off
Single-slot config means no concurrent agent inference.
Acceptable while Qwen3.6-27B dense is the primary model.
When migrating to Qwen3.6-35B-A3B-GGUF (MoE), revisit parallel_slots.
