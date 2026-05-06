# Benchmark Report

## Per-Run Results

| Variant | Query | Latency (s) | Cost (USD) | Quality Score | Citation Coverage | Failed | Notes |
|---|---|---:|---:|---:|---:|---|---|
| baseline | Explain multi-agent systems | 0.00 | 0.0010 |  | 0.00 | no | route=no-routes; sources=0; critic=no; errors=0 |
| multi-agent | Explain multi-agent systems | 0.00 |  |  |  | yes | Failed: test_benchmark_command_writes_report.<locals>.fake_run_multi_agent_state() got an unexpected keyword argument 'enable_critic' |

## Aggregate Summary

| Variant | Runs | Avg Latency (s) | Avg Cost (USD) | Avg Quality Score | Avg Citation Coverage | Failure Rate |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 0.00 | 0.0010 |  | 0.00 | 0.00 |
| multi-agent | 1 | 0.00 |  |  |  | 1.00 |

## Trace Artifacts

- baseline: Explain multi-agent systems -> `traces/baseline-benchmark-1.md`
