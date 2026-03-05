# Benchmark Results - profile_cd_real

> generated_at_utc: 2026-03-05T01:16:43+00:00
> mode: real API embedding/reranker execution

## profile_c

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 208 | 0.875 | 0.875 | 0.875 | 0.875 | 1675.6 | 0.0% | - |
| BEIR NFCorpus | 8 | 208 | 0.250 | 0.250 | 0.250 | 0.250 | 626.2 | 0.0% | - |

## profile_d

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 208 | 0.875 | 0.875 | 0.875 | 0.875 | 2106.6 | 0.0% | - |
| BEIR NFCorpus | 8 | 208 | 0.375 | 0.375 | 0.375 | 0.375 | 2751.1 | 0.0% | - |

## Phase 6 Gate

- overall_valid: true
- gate_mode: `api_tolerant`
- invalid_rate_threshold: 5.00%
- invalid_reasons: (none)
- invalid_count: 0 / 16 (0.00%)
- request_failed_count: 0 (0.00%)
