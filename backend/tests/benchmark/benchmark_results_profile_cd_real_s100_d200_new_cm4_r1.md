# Benchmark Results - profile_cd_real

> generated_at_utc: 2026-03-05T00:51:16+00:00
> mode: real API embedding/reranker execution

## profile_c

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.910 | 0.860 | 0.873 | 0.910 | 1026.9 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.250 | 0.164 | 0.185 | 0.250 | 848.2 | 1.0% | embedding_fallback_hash,embedding_request_failed |

## profile_d

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.920 | 0.904 | 0.908 | 0.920 | 2525.5 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.310 | 0.215 | 0.238 | 0.310 | 3018.4 | 0.0% | - |

## Phase 6 Gate

- overall_valid: true
- gate_mode: `api_tolerant`
- invalid_rate_threshold: 5.00%
- invalid_reasons: (none)
- invalid_count: 0 / 200 (0.00%)
- request_failed_count: 0 (0.00%)
