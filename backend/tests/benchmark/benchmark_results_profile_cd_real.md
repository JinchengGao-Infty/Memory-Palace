# Benchmark Results - profile_cd_real

> generated_at_utc: 2026-03-05T11:16:52+00:00
> mode: real API embedding/reranker execution

## profile_c

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 18 | 1.000 | 1.000 | 1.000 | 1.000 | 537.9 | 0.0% | - |

## profile_d

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 18 | 1.000 | 1.000 | 1.000 | 1.000 | 2898.6 | 0.0% | - |

## Phase 6 Gate

- overall_valid: true
- gate_mode: `strict`
- invalid_rate_threshold: 5.00%
- invalid_reasons: (none)
- invalid_count: 0 / 8 (0.00%)
- request_failed_count: 0 (0.00%)
