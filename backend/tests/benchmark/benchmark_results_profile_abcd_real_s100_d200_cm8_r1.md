# Benchmark Results - profile_abcd_real

> generated_at_utc: 2026-03-04T16:55:22+00:00
> mode: real execution (SQLiteClient.search_advanced + runtime profile env)

## Run Strategy

- dataset_scope: squad_v2_dev, beir_nfcorpus
- sample_size_requested: 100
- first_relevant_only: True
- extra_distractors: 200
- max_results: 10
- candidate_multiplier: 8
- metric_top_k: 10

## profile_a

- mode: `keyword`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.000 | 0.000 | 0.000 | 0.000 | 2.3 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.110 | 0.110 | 0.110 | 0.110 | 3.2 | 0.0% | - |

## profile_b

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.410 | 0.263 | 0.298 | 0.410 | 17.8 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.170 | 0.088 | 0.107 | 0.170 | 24.6 | 0.0% | - |

## profile_c

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.980 | 0.930 | 0.943 | 0.980 | 780.4 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.420 | 0.285 | 0.318 | 0.420 | 946.3 | 0.0% | - |

## profile_d

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.990 | 0.969 | 0.974 | 0.990 | 6699.9 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.450 | 0.332 | 0.360 | 0.450 | 6354.7 | 1.0% | reranker_request_failed |

## Phase 6 Gate (Profile D)

- overall_valid: true
- gate_mode: `api_tolerant`
- invalid_rate_threshold: 5.00%
- invalid_reasons: reranker_request_failed
- invalid_count: 1 / 200 (0.50%)
- request_failed_count: 1 (0.50%)

| Dataset | Valid | Invalid Reasons | Invalid Count | Invalid Rate | RequestFailed Count | RequestFailed Rate |
|---|---|---|---:|---:|---:|---:|
| SQuAD v2 Dev | PASS | - | 0 | 0.00% | 0 | 0.00% |
| BEIR NFCorpus | PASS | reranker_request_failed | 1 | 1.00% | 1 | 1.00% |

## A/B/C/D Comparison

| Dataset | A HR@10 | B HR@10 | C HR@10 | D HR@10 | A NDCG@10 | B NDCG@10 | C NDCG@10 | D NDCG@10 | A p95 | B p95 | C p95 | D p95 | D Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 0.000 | 0.410 | 0.980 | 0.990 | 0.000 | 0.298 | 0.943 | 0.974 | 2.3 | 17.8 | 780.4 | 6699.9 | PASS |
| BEIR NFCorpus | 0.110 | 0.170 | 0.420 | 0.450 | 0.110 | 0.107 | 0.318 | 0.360 | 3.2 | 24.6 | 946.3 | 6354.7 | INVALID |
