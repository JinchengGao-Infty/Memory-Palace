# Benchmark Results - profile_cd_real

> generated_at_utc: 2026-03-04T17:28:11+00:00
> mode: real API embedding/reranker execution

## profile_c

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.980 | 0.925 | 0.939 | 0.980 | 1187.4 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.420 | 0.285 | 0.318 | 0.420 | 998.1 | 0.0% | - |

## profile_d

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.990 | 0.964 | 0.971 | 0.990 | 4365.2 | 1.0% | reranker_request_failed |
| BEIR NFCorpus | 100 | 293 | 0.450 | 0.333 | 0.362 | 0.450 | 5060.8 | 0.0% | - |

## Phase 6 Gate

- overall_valid: true
- gate_mode: `api_tolerant`
- invalid_rate_threshold: 5.00%
- invalid_reasons: reranker_request_failed
- invalid_count: 1 / 200 (0.50%)
- request_failed_count: 1 (0.50%)
