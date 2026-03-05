# Benchmark Results - profile_cd_real

> generated_at_utc: 2026-03-04T17:59:13+00:00
> mode: real API embedding/reranker execution

## profile_c

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.980 | 0.930 | 0.943 | 0.980 | 974.3 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.420 | 0.285 | 0.318 | 0.420 | 1387.0 | 0.0% | - |

## profile_d

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.990 | 0.974 | 0.978 | 0.990 | 4562.4 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.450 | 0.332 | 0.360 | 0.450 | 5865.9 | 0.0% | - |

## Phase 6 Gate

- overall_valid: true
- gate_mode: `api_tolerant`
- invalid_rate_threshold: 5.00%
- invalid_reasons: (none)
- invalid_count: 0 / 200 (0.00%)
- request_failed_count: 0 (0.00%)
