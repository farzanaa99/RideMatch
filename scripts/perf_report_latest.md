# Performance Profile Report

| Metric | Value |
|---|---:|
| Assignments/sec | 2193.72 |
| p50 batch latency (ms) | 36.83 |
| p95 batch latency (ms) | 41.41 |
| p99 batch latency (ms) | 41.86 |
| Queue drain time (ms) | 41.98 |
| DB I/O micro-benchmark (ms) | 55.83 |
| Queue contention micro-benchmark (ms) | 1.50 |

## Bottleneck Ranking
- Database I/O: 55.83ms
- Scoring loop / matching: 41.41ms
- Queue contention: 1.50ms