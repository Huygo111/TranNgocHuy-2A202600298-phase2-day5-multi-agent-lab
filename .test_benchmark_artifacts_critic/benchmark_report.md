# Benchmark Report

## Per-Run Results

| Variant | Query | Latency (s) | Cost (USD) | Quality Score | Citation Coverage | Failed | Notes |
|---|---|---:|---:|---:|---:|---|---|
| baseline | Explain multi-agent systems | 0.00 |  |  | 0.00 | no | route=no-routes; sources=0; critic=no; errors=0 |
| multi-agent | Explain multi-agent systems | 0.00 |  |  | 1.00 | no | route=no-routes; sources=0; critic=no; errors=0 |
| multi-agent-critic | Explain multi-agent systems | 0.00 |  | 8.0 | 1.00 | no | route=no-routes; sources=0; critic=yes; errors=0 |

## Aggregate Summary

| Variant | Runs | Avg Latency (s) | Avg Cost (USD) | Avg Quality Score | Avg Citation Coverage | Failure Rate |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 0.00 |  |  | 0.00 | 0.00 |
| multi-agent | 1 | 0.00 |  |  | 1.00 | 0.00 |
| multi-agent-critic | 1 | 0.00 |  | 8.00 | 1.00 | 0.00 |

## Trace Artifacts

- baseline: Explain multi-agent systems -> `traces/baseline-benchmark-1.md`
- multi-agent: Explain multi-agent systems -> `traces/multi-agent-benchmark-1.md`
- multi-agent-critic: Explain multi-agent systems -> `traces/multi-agent-critic-benchmark-1.md`
