# Benchmark Results - profile_abcd_real

> generated_at_utc: 2026-03-05T00:51:16+00:00
> mode: real execution (SQLiteClient.search_advanced + runtime profile env)

## Run Strategy

- dataset_scope: squad_v2_dev, beir_nfcorpus
- sample_size_requested: 100
- first_relevant_only: True
- extra_distractors: 200
- max_results: 10
- candidate_multiplier: 4
- metric_top_k: 10

## profile_a

- mode: `keyword`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.000 | 0.000 | 0.000 | 0.000 | 2.1 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.110 | 0.110 | 0.110 | 0.110 | 3.0 | 0.0% | - |

## profile_b

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.400 | 0.243 | 0.280 | 0.400 | 16.3 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.090 | 0.036 | 0.049 | 0.090 | 19.3 | 0.0% | - |

## profile_c

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.910 | 0.860 | 0.873 | 0.910 | 1026.9 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.250 | 0.164 | 0.185 | 0.250 | 848.2 | 1.0% | embedding_fallback_hash,embedding_request_failed |

## profile_d

- mode: `hybrid`

| Dataset | Queries | Corpus Docs | HR@10 | MRR | NDCG@10 | Recall@10 | p95(ms) | Degrade Rate | Invalid Reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 100 | 295 | 0.920 | 0.904 | 0.908 | 0.920 | 2525.5 | 0.0% | - |
| BEIR NFCorpus | 100 | 293 | 0.310 | 0.215 | 0.238 | 0.310 | 3018.4 | 0.0% | - |

## Phase 6 Gate (Profile D)

- overall_valid: true
- gate_mode: `api_tolerant`
- invalid_rate_threshold: 5.00%
- invalid_reasons: (none)
- invalid_count: 0 / 200 (0.00%)
- request_failed_count: 0 (0.00%)

| Dataset | Valid | Invalid Reasons | Invalid Count | Invalid Rate | RequestFailed Count | RequestFailed Rate |
|---|---|---|---:|---:|---:|---:|
| SQuAD v2 Dev | PASS | - | 0 | 0.00% | 0 | 0.00% |
| BEIR NFCorpus | PASS | - | 0 | 0.00% | 0 | 0.00% |

## A/B/C/D Comparison

| Dataset | A HR@10 | B HR@10 | C HR@10 | D HR@10 | A NDCG@10 | B NDCG@10 | C NDCG@10 | D NDCG@10 | A p95 | B p95 | C p95 | D p95 | D Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| SQuAD v2 Dev | 0.000 | 0.400 | 0.910 | 0.920 | 0.000 | 0.280 | 0.873 | 0.908 | 2.1 | 16.3 | 1026.9 | 2525.5 | PASS |
| BEIR NFCorpus | 0.110 | 0.090 | 0.250 | 0.310 | 0.110 | 0.049 | 0.185 | 0.238 | 3.0 | 19.3 | 848.2 | 3018.4 | PASS |
