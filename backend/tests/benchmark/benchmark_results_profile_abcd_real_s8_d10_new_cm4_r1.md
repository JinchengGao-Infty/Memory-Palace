# Benchmark Results - profile_abcd_real

> generated_at_utc: 2026-03-05T01:01:27+00:00
> mode: real execution (SQLiteClient.search_advanced + runtime profile env)

## Run Strategy

- dataset_scope: squad_v2_dev, beir_nfcorpus
- sample_size_requested: 8
- first_relevant_only: True
- extra_distractors: 10
- max_results: 10
- candidate_multiplier: 4
- metric_top_k: 10

## profile_a

- mode: `keyword`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 18 | 0.000 | 0.000 | 0.000 | 0.000 | 1.9 | 0.0% | - |
| BEIR NFCorpus | 8 | 18 | 0.250 | 0.250 | 0.250 | 0.250 | 2.0 | 0.0% | - |

## profile_b

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 18 | 0.625 | 0.302 | 0.383 | 0.625 | 5.7 | 0.0% | - |
| BEIR NFCorpus | 8 | 18 | 0.750 | 0.478 | 0.542 | 0.750 | 6.2 | 0.0% | - |

## profile_c

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 18 | 1.000 | 1.000 | 1.000 | 1.000 | 787.2 | 0.0% | - |
| BEIR NFCorpus | 8 | 18 | 0.750 | 0.567 | 0.611 | 0.750 | 491.7 | 0.0% | - |

## profile_d

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 8 | 18 | 1.000 | 1.000 | 1.000 | 1.000 | 1964.2 | 0.0% | - |
| BEIR NFCorpus | 8 | 18 | 0.750 | 0.650 | 0.673 | 0.750 | 2212.3 | 0.0% | - |

## Phase 6 Gate (Profile D)

- overall_valid: true
- gate_mode: `api_tolerant`
- invalid_rate_threshold: 5.00%
- invalid_reasons: (none)
- invalid_count: 0 / 16 (0.00%)
- request_failed_count: 0 (0.00%)

| Dataset | Valid | Invalid Reasons | Invalid Count | Invalid Rate | RequestFailed Count | RequestFailed Rate |
|---|---|---|---:|---:|---:|---:|
| SQuAD v2 Dev | PASS | - | 0 | 0.00% | 0 | 0.00% |
| BEIR NFCorpus | PASS | - | 0 | 0.00% | 0 | 0.00% |

## A/B/C/D Comparison

| Dataset | A HR@10 | B HR@10 | C HR@10 | D HR@10 | A NDCG@10 | B NDCG@10 | C NDCG@10 | D NDCG@10 | A p95 | B p95 | C p95 | D p95 | D Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 0.000 | 0.625 | 1.000 | 1.000 | 0.000 | 0.383 | 1.000 | 1.000 | 1.9 | 5.7 | 787.2 | 1964.2 | PASS |
| BEIR NFCorpus | 0.250 | 0.750 | 0.750 | 0.750 | 0.250 | 0.542 | 0.611 | 0.673 | 2.0 | 6.2 | 491.7 | 2212.3 | PASS |
