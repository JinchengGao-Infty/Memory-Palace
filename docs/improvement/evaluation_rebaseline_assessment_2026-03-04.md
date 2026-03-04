# Evaluation Rebaseline Assessment (2026-03-04)

## 1. 结论

结论：**需要重测（Mandatory）**，且应按“先统一口径，再全量矩阵，再消融扩展”执行。  
原因不是单点回归，而是评测口径与当前实现状态发生了多处漂移：

1. `docs/EVALUATION.md` 仍是 2026-02 口径。
2. 当前核心 benchmark 产物已更新到 2026-03-03。
3. 真实 A/B/C/D 产物当前样本口径与文档口径不一致。
4. `profile c/d` 在本轮 docker smoke 采集中出现检索降级失败，不能直接复用旧“全 PASS”结论。

## 2. 本轮数据采集（已执行）

### 2.1 产物与口径核对

- `backend/tests/benchmark/profile_ab_metrics.json`
  - `generated_at_utc=2026-03-03T16:03:24+00:00`
  - `sample_size=100`
- `backend/tests/benchmark/profile_abcd_real_metrics.json`
  - `generated_at_utc=2026-03-03T10:25:44+00:00`
  - `sample_size_requested=1`
  - `dataset_scope=squad_v2_dev`
- `backend/tests/datasets/manifests/`
  - 已落盘 7 份 manifest（`squad_v2_dev`、`dailydialog`、`msmarco_passages`、`beir_nfcorpus`、`beir_nq`、`beir_hotpotqa`、`beir_fiqa`）

### 2.2 旧仓数据复用核对

源目录：`/Users/yangjunjie/Desktop/clawmemo/nocturne_memory`

- `backend/tests/datasets/**`：与当前仓库内容一致，可视为已迁移完成。
- `backend/tests/benchmark/*.json|*.md`：可作为历史对照，不建议直接覆盖当前 `new/benchmark` 口径。
- `.env`/profile 脚本：与当前配置矩阵存在差异，不建议直接替换。

## 3. 首轮验证命令与结果

### 3.1 Benchmark 与契约快速验证

```bash
cd Memory-Palace/backend
.venv/bin/pytest tests/benchmark/test_dataset_integrity.py -q
.venv/bin/pytest tests/benchmark/test_benchmark_public_datasets_profiles.py -q -k small_gate
.venv/bin/pytest tests/benchmark/test_write_guard_llm_toggle.py -q
.venv/bin/pytest tests/benchmark/test_compact_context_llm_toggle.py -q
.venv/bin/pytest tests/benchmark/test_benchmark_degradation_injection.py -q
.venv/bin/pytest tests/benchmark/test_search_memory_contract_regression.py -q
.venv/bin/pytest tests/benchmark/test_profile_abcd_real_runner.py -q
```

结果汇总：

- `test_dataset_integrity.py`：`2 passed`
- `small_gate`：`1 passed, 1 deselected`
- `test_write_guard_llm_toggle.py`：`7 passed`
- `test_compact_context_llm_toggle.py`：`8 passed`
- `test_benchmark_degradation_injection.py`：`4 passed`
- `test_search_memory_contract_regression.py`：`2 passed`
- `test_profile_abcd_real_runner.py`：`5 passed`

### 3.2 Frontend 契约快速验证

```bash
cd Memory-Palace/frontend
npm run test -- src/lib/api.contract.test.js
```

结果：`8 passed`

### 3.3 Post-change checks 数据采集

```bash
bash new/run_post_change_checks.sh --skip-sse --skip-frontend --review-summary "assessment baseline 2026-03-04"
bash new/run_post_change_checks.sh --with-docker --docker-profile a --skip-sse --skip-frontend --review-summary "assessment docker profile-a 2026-03-04"
bash new/run_post_change_checks.sh --with-docker --docker-profile b --skip-sse --skip-frontend --review-summary "assessment docker profile-b 2026-03-04"
bash new/run_post_change_checks.sh --with-docker --docker-profile c --runtime-env-mode none --allow-runtime-env-injection --runtime-env-file /Users/yangjunjie/Desktop/clawmemo/nocturne_memory/.env --skip-sse --skip-frontend --review-summary "assessment docker profile-c injected env 2026-03-04"
bash new/run_post_change_checks.sh --with-docker --docker-profile d --runtime-env-mode none --allow-runtime-env-injection --runtime-env-file /Users/yangjunjie/Desktop/clawmemo/nocturne_memory/.env --skip-sse --skip-frontend --review-summary "assessment docker profile-d injected env 2026-03-04"
```

结果：

- baseline：`PASS=9, FAIL=0, SKIP=2`
- profile `a`：`PASS=11, FAIL=0, SKIP=2`
- profile `b`：`PASS=11, FAIL=0, SKIP=2`
- profile `c`：`PASS=10, FAIL=1, SKIP=2`
- profile `d`：`PASS=10, FAIL=1, SKIP=2`
- 对应 run：
  - baseline：`Run 20260303T170441Z-pid52644-r17917`
  - `a`：`Run 20260303T170508Z-pid52900-r30022`
  - `b`：`Run 20260303T170527Z-pid53261-r102`
  - `c`：`Run 20260303T170548Z-pid53619-r30950`
  - `d`：`Run 20260303T170629Z-pid54153-r5741`

`profile c/d` 失败项一致：`deployment.docker.smoke` 中 `observability.search probe: degraded=True`，`degrade_reasons=['embedding_request_failed','embedding_fallback_hash']`。

说明：该组失败来自 `runtime-env-mode none + --allow-runtime-env-injection` 口径。此口径会保留 C/D 模板中的 `RETRIEVAL_EMBEDDING_BACKEND=router`，在“本地 router 无 embedding/reranker 模型”时会触发上述 degraded 信号。

### 3.4 全量矩阵复验（按本地 C/D 联调约定）

```bash
cd Memory-Palace/backend
.venv/bin/pytest tests -q
.venv/bin/pytest tests/benchmark -q

cd ../frontend
npm run test
npm run build

cd ../../
bash new/run_post_change_checks.sh --with-docker --docker-profile a --review-summary "full matrix profile-a 2026-03-04"
bash new/run_post_change_checks.sh --with-docker --docker-profile b --review-summary "full matrix profile-b 2026-03-04"
bash new/run_post_change_checks.sh --with-docker --docker-profile c --runtime-env-mode file --runtime-env-file /Users/yangjunjie/Desktop/clawmemo/nocturne_memory/.env --allow-runtime-env-debug --review-summary "full matrix profile-c file-mode 2026-03-04"
bash new/run_post_change_checks.sh --with-docker --docker-profile d --runtime-env-mode file --runtime-env-file /Users/yangjunjie/Desktop/clawmemo/nocturne_memory/.env --allow-runtime-env-debug --review-summary "full matrix profile-d file-mode 2026-03-04"
```

结果汇总：

- backend 全量：`365 passed`
- benchmark 全量：`48 passed`
- frontend：`47 passed`，build `pass`
- profile `a`：`PASS=13, FAIL=0, SKIP=0`
- profile `b`：`PASS=13, FAIL=0, SKIP=0`
- profile `c`（file mode + nocturne env）：`PASS=13, FAIL=0, SKIP=0`
- profile `d`（file mode + nocturne env）：`PASS=13, FAIL=0, SKIP=0`
- 对应 run：
  - `a`：`Run 20260303T171755Z-pid63089-r19095`
  - `b`：`Run 20260303T171822Z-pid63470-r5152`
  - `c`：`Run 20260303T171846Z-pid64248-r7609`
  - `d`：`Run 20260303T171918Z-pid65654-r15095`

## 4. 覆盖矩阵（当前状态）

判定规则：

- `Covered`：有明确可执行门禁或测试锚点
- `Partial`：只有间接覆盖或未形成稳定门禁
- `Missing`：无可执行验证锚点

| 维度 | 状态 | 说明 |
|---|---|---|
| macOS | Partial | 有模板与报告，但缺“本轮发布级 smoke 绿灯”闭环 |
| Windows | Partial | CI 有 `windows-latest`，但缺本轮可追溯 smoke 结果沉淀 |
| Profile a | Covered | docker profile gate 可执行且本轮通过 |
| Profile b | Covered | docker profile gate 可执行且本轮通过 |
| Profile c | Partial | 本轮 smoke 存在降级失败 |
| Profile d | Partial | 本轮 smoke 存在降级失败 |
| backend | Covered | pytest + benchmark 契约完整 |
| frontend | Covered | vitest + build + API contract 可执行 |
| scripts | Partial | 主要被门禁间接覆盖，缺脚本级独立测试集 |
| docker | Covered | compose config + smoke 已集成到门禁 |
| snapshots | Partial | 有快照/回滚验证，但非默认门禁主链 |
| MCP tools | Covered | 工具集合契约 + hold/mcp 错误契约覆盖 |
| skills | Missing | 当前仅文档策略，无仓内可执行 skill 测试 |

补充：若按“本地 C/D 联调约定”（`runtime-env-mode file` + nocturne env）执行，`profile c/d` 当前可达 `PASS=13, FAIL=0, SKIP=0`；此时 `c/d` 的状态可视为“本地联调覆盖已达成”，但仍不等价于“上线 router 环境已验证”。

### 4.1 Phase B 产物与补充门禁（已执行）

执行项 1：标准化 benchmark 报告重生成

```bash
bash new/benchmark/run_bench.sh --source-report new/real_data_test_report.md --output-dir new/benchmark --update-release-gate
```

结果：

- 产物已更新：`run_manifest.json`、`quality_report.json`、`perf_report.json`、`long_memory_report.json`
- `run_id=20260303T173256Z`
- `quality gates.hybrid_hit_rate_ge_keyword=true`
- `perf gates.overall=true`

执行项 2：legacy 基线归档（历史对照）

```bash
mkdir -p new/benchmark/legacy_archive
cp /Users/yangjunjie/Desktop/clawmemo/nocturne_memory/backend/tests/benchmark/*.{json,md} new/benchmark/legacy_archive/
```

结果：已归档 15 个历史 benchmark 报告文件（json/md）。

执行项 3：补充 profile/质量门禁分组测试

```bash
cd Memory-Palace/backend
.venv/bin/pytest tests/benchmark/test_benchmark_retrieval_profiles.py -q
.venv/bin/pytest tests/benchmark/test_benchmark_latency_profiles.py -q
.venv/bin/pytest tests/benchmark/test_write_guard_quality_metrics.py -q
.venv/bin/pytest tests/benchmark/test_intent_accuracy_metrics.py -q
.venv/bin/pytest tests/benchmark/test_compact_context_gist_quality.py -q
```

结果：

- `test_benchmark_retrieval_profiles.py`: `4 passed`
- `test_benchmark_latency_profiles.py`: `4 passed`
- `test_write_guard_quality_metrics.py`: `1 passed`
- `test_intent_accuracy_metrics.py`: `1 passed`
- `test_compact_context_gist_quality.py`: `1 passed`

## 5. 扩展数据集与消融设计（建议执行）

### 5.1 数据集层

必跑（当前仓库已有处理链）：

1. `squad_v2_dev`
2. `dailydialog`
3. `msmarco_passages`
4. `beir_nfcorpus`
5. `beir_nq`
6. `beir_hotpotqa`
7. `beir_fiqa`

执行建议：

- 统一 `sample_size` 至 `100/200/500` 三档。
- 保持固定随机种子，确保 profile 与开关对比可复现。

### 5.2 消融层

建议最小消融矩阵：

1. 检索路径：`keyword` vs `hybrid` vs `semantic`
2. embedding：`hash` vs `router/api`
3. reranker：`on` vs `off`
4. Write Guard LLM：`on` vs `off`（含失败注入）
5. Compact Context LLM：`on` vs `off`（含 fallback 链）
6. vec engine：`legacy` vs `vec`（同 profile off/on）
7. degrade 注入：`embedding_request_failed` / `embedding_fallback_hash` / `reranker_request_failed`

### 5.3 指标层

除当前 `HR@10/MRR/NDCG@10/Recall@10/p50/p95` 外，建议统一纳入：

1. `HR@5`
2. `p99`
3. `degrade_rate`
4. `degrade_reasons` 分布
5. `invalid_reasons` 分布
6. `latency_improvement_ratio`（vec off/on）
7. `quality_non_regression_all`（vec off/on）
8. `fallback_legacy_rows`（vec off/on）
9. `wal_failure_rate`、`retry_rate_p95`、`wal_vs_delete_tps_ratio`、`persistence_gap`

## 6. 下一步执行顺序

### Phase A（先收敛口径）

1. 将真实 A/B/C/D 跑回与文档一致的样本规模（至少恢复到“多数据集 + 非 1 样本”）。
2. 明确 `profile c/d` 当前外部链路降级原因（网络、鉴权、模型可达性、路由配置）。

### Phase B（全量矩阵）

1. 跑全量 benchmark（7 数据集 × 4 profile × 关键开关）。
2. 产出统一 JSON + Markdown 报告（建议保留到 `new/benchmark`，并保留一份 `legacy_archive` 历史对照）。

### Phase C（文档回写）

1. 更新 `docs/EVALUATION.md` 的主表与时间戳。
2. 将“历史基线”与“当前主线”分层展示，避免旧数据覆盖新结论。

## 7. 已知限制

1. 本轮为“评估与采集阶段”，未执行完整跨平台（真实 Windows 主机）端到端复测。
2. 当前仓库已有未提交改动（主要在 backend/new 日志相关文件），本次未触碰这些既有改动，仅新增评估文档与 `EVALUATION` 状态说明。

## 8. 执行状态（按本轮用户确认）

| 项目 | 状态 | 说明 |
|---|---|---|
| Windows 实机复测 | Not Required | 本轮用户明确不执行 |
| `EVALUATION.md` 主表重写 | Deferred | 本轮用户明确暂不改 |
| Phase A（口径收敛） | Done | 已区分 `none+injection` 与 `file+nocturne env` 两种口径并给出通过/失败证据 |
| Phase B（全量矩阵与产物） | Done | 已完成 backend/frontend/benchmark/docker a/b/c/d + `new/benchmark` 重生成 + legacy 归档 |
| Phase B.1（扩展消融：sample-size，strict 历史口径） | Done | `s100/s200/s500` 均已完成并落盘；`s200` 前两次在工作区缓存目录报 `readonly`/`disk I/O`，第三次切到 `/tmp` workdir 成功。该阶段用于确认大样本下 `reranker_request_failed` 的复现特征，结果已汇总到 `docs/improvement/evaluation_ablation_results_2026-03-04.md`。 |
| Phase B.2（api_tolerant 门禁重测） | Done | 已切换 `edgefn reranker` 并启用 `BENCHMARK_PHASE6_GATE_MODE=api_tolerant`（阈值 `<=5%`），重跑 `s100/s200/s500`：`phase6.gate.valid` 全为 `true`；实际 `request_failed_rate` 分别为 `1.0%`、`0.25%`、`0.2%`。产物目录：`new/benchmark/ablation/retest_edgefn_t20_api_tolerant_venv_20260304_142636`。 |
| Phase C（主表回写） | Deferred | 按用户要求暂缓，只保留状态提示与独立评估报告 |
