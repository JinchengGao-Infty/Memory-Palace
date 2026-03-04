# Evaluation Ablation Results (2026-03-04)

## 1. 范围与约束

- 不重写 `docs/EVALUATION.md` 主表；新评估结果独立记录在本文件。
- 本地 `profile c/d` 固定使用 `runtime-env-mode=file` + `runtime-env-file=/Users/yangjunjie/Desktop/clawmemo/nocturne_memory/.env`。
- 本地 `c/d` 的 LLM 口径固定使用上述 `.env` 中的 `gpt-5.2`；上线时仍以 router 配置优先，缺失时 fallback。

### 1.1 术语映射（避免与主线 Phase A/B/C/D 混淆）

- 本文中的 `phase6` 指 benchmark 历史分阶段命名里的 “Profile D 有效性门（gate）”。
- `phase6.gate.valid=true` 代表本轮 `profile_d` 全数据集未命中失效原因。
- `phase6.gate.invalid_reasons` 当前关注三类：`embedding_fallback_hash`、`embedding_request_failed`、`reranker_request_failed`。
- `phase6` 是评测结果字段与报告字段，不等同于当前项目实施主线中的 `Phase A/B/C/D`。

## 2. 已完成门禁矩阵（A/B/C/D）

| Profile | Run ID | PASS | FAIL | SKIP | Runtime Env Mode |
|---|---|---:|---:|---:|---|
| a | `20260303T171755Z-pid63089-r19095` | 13 | 0 | 0 | `none` |
| b | `20260303T171822Z-pid63470-r5152` | 13 | 0 | 0 | `none` |
| c | `20260303T171846Z-pid64248-r7609` | 13 | 0 | 0 | `file` (`/Users/yangjunjie/Desktop/clawmemo/nocturne_memory/.env`) |
| d | `20260303T171918Z-pid65654-r15095` | 13 | 0 | 0 | `file` (`/Users/yangjunjie/Desktop/clawmemo/nocturne_memory/.env`) |

证据来源：`new/release_gate_log.md`、`new/verification_log.md`。

## 3. 基线快照（当前可复现）

### 3.1 `profile_ab_metrics.json`（`sample_size=100`）

- `generated_at_utc=2026-03-03T17:33:15+00:00`
- `phase6.gate.valid=true`

| profile | dataset | hr@10 | mrr | ndcg@10 | recall@10 | p95(ms) | degrade_rate | invalid_reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|
| profile_a | msmarco_passages | 0.333 | 0.333 | 0.333 | 0.333 | 2.1 | 0.0 | - |
| profile_a | beir_nfcorpus | 0.300 | 0.300 | 0.300 | 0.300 | 2.6 | 0.0 | - |
| profile_a | squad_v2_dev | 0.150 | 0.150 | 0.150 | 0.150 | 3.0 | 0.0 | - |
| profile_b | msmarco_passages | 0.867 | 0.658 | 0.696 | 0.850 | 3.7 | 0.0 | - |
| profile_b | beir_nfcorpus | 1.000 | 0.828 | 0.850 | 0.975 | 4.7 | 0.0 | - |
| profile_b | squad_v2_dev | 1.000 | 0.765 | 0.822 | 1.000 | 3.9 | 0.0 | - |
| profile_cd | msmarco_passages | 0.867 | 0.658 | 0.696 | 0.850 | 3.7 | 0.0 | - |
| profile_cd | beir_nfcorpus | 1.000 | 0.828 | 0.850 | 0.975 | 4.7 | 0.0 | - |
| profile_cd | squad_v2_dev | 1.000 | 0.765 | 0.822 | 1.000 | 3.9 | 0.0 | - |

### 3.2 `profile_abcd_real_metrics.json`（历史真实口径）

- `generated_at_utc=2026-03-03T10:25:44+00:00`
- `sample_size_requested=1`
- `dataset_scope=squad_v2_dev`
- `phase6.gate.valid=true`

| profile | dataset | hr@10 | mrr | ndcg@10 | recall@10 | p95(ms) | degrade_rate | invalid_reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|
| profile_a | squad_v2_dev | 0.000 | 0.000 | 0.000 | 0.000 | 2.219583 | 0.0 | - |
| profile_b | squad_v2_dev | 1.000 | 1.000 | 1.000 | 1.000 | 5.535125 | 0.0 | - |
| profile_c | squad_v2_dev | 1.000 | 1.000 | 1.000 | 1.000 | 3167.083250 | 1.0 | `embedding_fallback_hash;embedding_request_failed` |
| profile_d | squad_v2_dev | 1.000 | 1.000 | 1.000 | 1.000 | 1732.147250 | 0.0 | - |

## 4. 扩展消融（已完成）

### 4.1 `s100`（已完成）

- 产物：
  - `new/benchmark/ablation/profile_abcd_real_metrics_s100.json`
  - `new/benchmark/ablation/benchmark_results_profile_abcd_real_s100.md`
  - `new/benchmark/ablation/benchmark_results_profile_cd_real_s100.md`
  - `new/benchmark/ablation/benchmark_abcd_real_analysis_s100.md`
- `generated_at_utc=2026-03-03T19:55:05+00:00`
- `sample_size_requested=100`
- `dataset_scope=squad_v2_dev,beir_nfcorpus`
- `phase6.gate.valid=true`

| profile | hr@10(avg) | mrr(avg) | ndcg@10(avg) | recall@10(avg) | p95(avg, ms) | invalid_rows | max_degrade_rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| profile_a | 0.055 | 0.055 | 0.055 | 0.055 | 2.577 | 0 | 0.00 |
| profile_b | 0.125 | 0.081 | 0.092 | 0.125 | 12.644 | 0 | 0.00 |
| profile_c | 0.275 | 0.246 | 0.253 | 0.275 | 868.103 | 1 | 0.01 |
| profile_d | 0.290 | 0.268 | 0.273 | 0.290 | 2672.499 | 0 | 0.00 |

`s100` 关键异常点：

| profile | dataset | degrade_rate | invalid_reasons |
|---|---|---:|---|
| profile_c | beir_nfcorpus | 0.01 | `embedding_fallback_hash;embedding_request_failed` |

### 4.2 `s200`（已完成，串行重试后成功）

- 尝试 1：
  - `workdir=.cache_s200`
  - 失败：`sqlite3.OperationalError: attempt to write a readonly database`
- 尝试 2：
  - `workdir=.cache_s200_retry1`
  - 失败：`sqlite3.OperationalError: disk I/O error`
  - 日志：`new/benchmark/ablation/run_s200_retry1.log`
- 尝试 3：
  - `workdir=/tmp/benchmark_ablation_cache_s200`
  - 日志：`new/benchmark/ablation/run_s200_retry2_tmp.log`
  - 结果：完成并落盘

- 产物：
  - `new/benchmark/ablation/profile_abcd_real_metrics_s200.json`
  - `new/benchmark/ablation/benchmark_results_profile_abcd_real_s200.md`
  - `new/benchmark/ablation/benchmark_results_profile_cd_real_s200.md`
  - `new/benchmark/ablation/benchmark_abcd_real_analysis_s200.md`
- `generated_at_utc=2026-03-03T20:36:36+00:00`
- `sample_size_requested=200`
- `dataset_scope=squad_v2_dev,beir_nfcorpus`
- `phase6.gate.valid=false`
- `phase6.gate.invalid_reasons=[reranker_request_failed]`

| profile | hr@10(avg) | mrr(avg) | ndcg@10(avg) | recall@10(avg) | p95(avg, ms) | invalid_rows | max_degrade_rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| profile_a | 0.053 | 0.046 | 0.047 | 0.053 | 4.673 | 0 | 0.000 |
| profile_b | 0.095 | 0.054 | 0.064 | 0.095 | 15.582 | 0 | 0.000 |
| profile_c | 0.205 | 0.170 | 0.179 | 0.205 | 873.948 | 1 | 0.005 |
| profile_d | 0.225 | 0.199 | 0.205 | 0.225 | 2466.092 | 1 | 0.005 |

`s200` 关键异常点：

| profile | dataset | degrade_rate | invalid_reasons |
|---|---|---:|---|
| profile_c | beir_nfcorpus | 0.005 | `embedding_fallback_hash;embedding_request_failed` |
| profile_d | beir_nfcorpus | 0.005 | `reranker_request_failed` |

### 4.3 `s500`（已完成）

- 执行口径：
  - `workdir=/tmp/benchmark_ablation_cache_s500`
  - 日志：`new/benchmark/ablation/run_s500_tmp.log`
  - 监控中 `profile_d.db` 未单独出现属正常：runner 代码中 `profile_d` 复用 `profile_c` 数据库（`reuse_data_from=profile_c`）。
- 产物：
  - `new/benchmark/ablation/profile_abcd_real_metrics_s500.json`
  - `new/benchmark/ablation/benchmark_results_profile_abcd_real_s500.md`
  - `new/benchmark/ablation/benchmark_results_profile_cd_real_s500.md`
  - `new/benchmark/ablation/benchmark_abcd_real_analysis_s500.md`
- `generated_at_utc=2026-03-03T21:56:54+00:00`
- `sample_size_requested=500`
- `dataset_scope=squad_v2_dev,beir_nfcorpus`
- `phase6.gate.valid=false`
- `phase6.gate.invalid_reasons=[reranker_request_failed]`

| profile | hr@10(avg) | mrr(avg) | ndcg@10(avg) | recall@10(avg) | p95(avg, ms) | invalid_rows | max_degrade_rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| profile_a | 0.047 | 0.040 | 0.042 | 0.047 | 4.118 | 0 | 0.000 |
| profile_b | 0.072 | 0.040 | 0.047 | 0.072 | 14.652 | 0 | 0.000 |
| profile_c | 0.149 | 0.123 | 0.130 | 0.149 | 1003.736 | 2 | 0.004 |
| profile_d | 0.172 | 0.148 | 0.154 | 0.172 | 4856.580 | 1 | 0.006 |

`s500` 关键异常点：

| profile | dataset | degrade_rate | invalid_reasons |
|---|---|---:|---|
| profile_c | squad_v2_dev | 0.004 | `embedding_fallback_hash;embedding_request_failed` |
| profile_c | beir_nfcorpus | 0.002 | `embedding_fallback_hash;embedding_request_failed` |
| profile_d | squad_v2_dev | 0.006 | `reranker_request_failed` |

### 4.4 `s100/s200/s500` 汇总

| sample_size | phase6.gate.valid | phase6.invalid_reasons | profile_c invalid_rows | profile_d invalid_rows |
|---:|---|---|---:|---:|
| 100 | true | - | 1 | 0 |
| 200 | false | `reranker_request_failed` | 1 | 1 |
| 500 | false | `reranker_request_failed` | 2 | 1 |

| sample_size | profile_b hr@10 | profile_c hr@10 | profile_d hr@10 | profile_d p95(ms) |
|---:|---:|---:|---:|---:|
| 100 | 0.125 | 0.275 | 0.290 | 2672.499 |
| 200 | 0.095 | 0.205 | 0.225 | 2466.092 |
| 500 | 0.072 | 0.149 | 0.172 | 4856.580 |

## 5. 结果聚合命令（复算口径保留）

```bash
find new/benchmark/ablation -type f -name 'profile_abcd_real_metrics_s*.json' -print0 \
| xargs -0 -r jq -r '
  . as $doc
  | $doc.profiles | to_entries[] | .key as $profile | .value.rows[]
  | (try (input_filename|capture("_s(?<s>[0-9]+)\\.json$").s|tonumber) catch ($doc.sample_size_requested // .sample_size)) as $s
  | [$s, $profile, .dataset, .quality.hr_at_10, .quality.mrr, .quality.ndcg_at_10, .quality.recall_at_10, .latency_ms.p95, .degradation.degrade_rate, (.degradation.invalid_reasons|join(";")), $doc.phase6.gate.valid]
  | @tsv'
```

```bash
jq -n '
  [inputs as $doc
   | $doc.profiles | to_entries[] | .key as $profile | .value.rows[]
   | { sample_size: ($doc.sample_size_requested // .sample_size), profile: $profile,
       hr10: .quality.hr_at_10, mrr: .quality.mrr, ndcg10: .quality.ndcg_at_10, recall10: .quality.recall_at_10,
       p95: .latency_ms.p95, queries: .degradation.queries, degraded: .degradation.degraded,
       invalid_reasons: .degradation.invalid_reasons, phase6_gate_valid: $doc.phase6.gate.valid } ]
  | group_by([.sample_size, .profile])
  | map({
      sample_size: .[0].sample_size, profile: .[0].profile,
      hr10: ((map(.hr10)|add)/length), mrr: ((map(.mrr)|add)/length),
      ndcg10: ((map(.ndcg10)|add)/length), recall10: ((map(.recall10)|add)/length),
      p95: ((map(.p95)|add)/length),
      degrade_rate: ((map(.degraded)|add)/(map(.queries)|add)),
      invalid_reasons: (map(.invalid_reasons[])|unique),
      phase6_gate_valid: (map(.phase6_gate_valid)|index(false)|not)
    })' new/benchmark/ablation/profile_abcd_real_metrics_s*.json
```

## 6. 下一步

1. 对 `s200/s500` 的 `reranker_request_failed` 做单独归因（模型可达性/网络/路由降级链路）。
2. 扩展到 7 个通用数据集并保持 `100/200/500` 三档 sample-size。
3. 在 Mac/Windows 分开复跑 profile `a/b/c/d` 并对齐前后端、docker、scripts、snapshots、mcp、skills 覆盖矩阵。

## 7. 重测结果（同口径复跑，2026-03-04）

重测目录：`new/benchmark/ablation/retest_20260304_063201`

### 7.1 `s200_retest`

- 产物：
  - `profile_abcd_real_metrics_s200_retest.json`
  - `benchmark_results_profile_abcd_real_s200_retest.md`
  - `benchmark_results_profile_cd_real_s200_retest.md`
  - `benchmark_abcd_real_analysis_s200_retest.md`
- `generated_at_utc=2026-03-03T23:08:22+00:00`
- `phase6.gate.valid=true`
- `phase6.gate.invalid_reasons=[]`

| profile | hr@10(avg) | ndcg@10(avg) | p95(avg, ms) |
|---|---:|---:|---:|
| profile_a | 0.053 | 0.047 | 3.212 |
| profile_b | 0.095 | 0.064 | 12.981 |
| profile_c | 0.205 | 0.179 | 833.162 |
| profile_d | 0.225 | 0.205 | 2532.267 |

结论：`s200` 在本轮重测中恢复为 `phase6 gate=true`，`reranker_request_failed` 未复现。

### 7.2 `s500_retest`

- 产物：
  - `profile_abcd_real_metrics_s500_retest.json`
  - `benchmark_results_profile_abcd_real_s500_retest.md`
  - `benchmark_results_profile_cd_real_s500_retest.md`
  - `benchmark_abcd_real_analysis_s500_retest.md`
- `generated_at_utc=2026-03-04T01:08:34+00:00`
- `phase6.gate.valid=false`
- `phase6.gate.invalid_reasons=[reranker_request_failed]`

| profile | hr@10(avg) | ndcg@10(avg) | p95(avg, ms) |
|---|---:|---:|---:|
| profile_a | 0.047 | 0.042 | 4.112 |
| profile_b | 0.072 | 0.047 | 12.694 |
| profile_c | 0.149 | 0.131 | 804.715 |
| profile_d | 0.172 | 0.154 | 2699.618 |

结论：`s500` 重测后 `phase6 gate=false` 仍复现，且失效原因稳定为 `reranker_request_failed`（仅 `SQuAD v2 Dev` 行触发）。

### 7.3 `s500_timeout40`（仅提升远端超时后复跑）

- 执行口径：
  - 运行时覆盖：`RETRIEVAL_REMOTE_TIMEOUT_SEC=40`
  - 目录：`new/benchmark/ablation/retest_timeout40_20260304_092110`
  - 产物：
    - `profile_abcd_real_metrics_s500_timeout40.json`
    - `benchmark_results_profile_abcd_real_s500_timeout40.md`
    - `benchmark_results_profile_cd_real_s500_timeout40.md`
    - `benchmark_abcd_real_analysis_s500_timeout40.md`
- `generated_at_utc=2026-03-04T02:41:24+00:00`
- `phase6.gate.valid=false`
- `phase6.gate.invalid_reasons=[reranker_request_failed]`

`profile_d` 关键退化行：

| dataset | degraded | degrade_rate | invalid_reasons |
|---|---:|---:|---|
| squad_v2_dev | 0 | 0.000 | - |
| beir_nfcorpus | 1 | 0.002 | `reranker_request_failed` |

对比 `s500_retest`（默认超时）：

| run | phase6.gate.valid | invalid_reasons | 触发数据集 | degrade_rate |
|---|---|---|---|---:|
| `s500_retest` | false | `reranker_request_failed` | `squad_v2_dev` | 0.004 |
| `s500_timeout40` | false | `reranker_request_failed` | `beir_nfcorpus` | 0.002 |

结论：仅将远端超时从默认值提高到 `40s` 未能消除 `reranker_request_failed`，因此该问题**不只是“等待时长太短”**，更可能是大样本下 reranker 链路稳定性问题（超时/可用性抖动）。

## 8. `edgefn reranker + api_tolerant` 重测（最终口径）

- 执行目录：`new/benchmark/ablation/retest_edgefn_t20_api_tolerant_venv_20260304_142636`
- 重测配置：
  - `RETRIEVAL_RERANKER_API_BASE=https://api.edgefn.net/v1`
  - `RETRIEVAL_RERANKER_MODEL=Qwen3-Reranker-8B`
  - `BENCHMARK_PHASE6_GATE_MODE=api_tolerant`
  - `BENCHMARK_PHASE6_INVALID_RATE_THRESHOLD=0.05`
- 说明：本轮评估门禁以“API 可容忍口径”判定稳定性；仍完整记录实际 `request_failed` 比例。

### 8.1 C/D 指标汇总（两数据集均值）

| sample_size | profile_c hr@10 | profile_c mrr | profile_c ndcg@10 | profile_c p95(ms) | profile_d hr@10 | profile_d mrr | profile_d ndcg@10 | profile_d p95(ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 0.280 | 0.247 | 0.255 | 831.4 | 0.295 | 0.268 | 0.275 | 2903.9 |
| 200 | 0.205 | 0.170 | 0.179 | 885.1 | 0.225 | 0.199 | 0.205 | 2860.4 |
| 500 | 0.149 | 0.124 | 0.130 | 871.2 | 0.172 | 0.148 | 0.154 | 2936.7 |

### 8.2 稳定性与门禁汇总（phase6）

| sample_size | phase6.gate.valid | request_failed_count / query_count | request_failed_rate | invalid_reason_counts |
|---:|---|---:|---:|---|
| 100 | true | 2 / 200 | 1.0% | `reranker_request_failed: 2` |
| 200 | true | 1 / 400 | 0.25% | `reranker_request_failed: 1` |
| 500 | true | 2 / 1000 | 0.2% | `reranker_request_failed: 2` |

### 8.3 结论（本轮最终）

1. 在 `api_tolerant<=5%` 门禁下，`s100/s200/s500` 全部通过（`phase6.gate.valid=true`）。
2. `request_failed` 全部来自 `reranker_request_failed`，且实际比例均显著低于 `5%` 阈值。
3. 该结论用于“外部 API 链路可用性口径”；若使用历史 `strict` 零容忍门禁，则大样本场景仍可能被小比例抖动判为失败。
