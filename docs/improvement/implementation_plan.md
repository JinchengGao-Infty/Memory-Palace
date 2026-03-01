# Memory Palace 最终融合改进计划

> 融合 **Claude Code Memory** 🔵 + **OpenClaw Memory** 🟠 + **局限性修复** 🔴 + **mem0 对比评估** 📊

---

## 第一部分：mem0 对比评估

### mem0 是什么

mem0 是 AI 应用的通用记忆层（Apache 2.0），定位为"给任何 AI 应用添加记忆能力"的中间件。核心特点：

- **LLM 驱动管线**：`add()` 时 LLM 自动从对话中提取事实 → 冲突解决（ADD/UPDATE/DELETE）→ 并行写入
- **Graph Memory**：Neo4j/Kuzu/Memgraph 实体关系图谱
- **24+ 向量库**：Qdrant（默认）、Pinecone、ChromaDB、PGVector、Redis、Weaviate…
- **多级会话作用域**：`user_id` / `agent_id` / `app_id` / `run_id` 四维过滤
- **双模式部署**：托管平台 `api.mem0.ai` + 完全自托管

### MP vs mem0 对比

| 维度 | Memory Palace | mem0 | 评价 |
|---|---|---|---|
| **定位** | MCP 原生记忆操作系统 | 通用 AI 记忆中间件 | 赛道不同 |
| **接入方式** | MCP 协议（标准化） | Python/TS SDK + REST API | MP 对 MCP 生态更原生 |
| **写入安全** | ✅ Write Guard + 快照 + 回滚 | ❌ 无（LLM 直接写入） | **MP 远更强** |
| **可观测性** | ✅ 四视图仪表盘 | ❌ 基本无 | **MP 远更强** |
| **治理循环** | ✅ Review + 活力衰减 + 清理 | ❌ 仅 history 日志 | **MP 远更强** |
| **检索引擎** | keyword + semantic + reranker + 意图分类 | 向量相似度 + 可选 reranker | **MP 更强** |
| **事实提取** | ❌ 需 Agent 显式写入 | ✅ LLM 自动提取+冲突解决 | **mem0 更强** |
| **Graph Memory** | ❌ 无 | ✅ 实体关系图谱 | **mem0 更强** |
| **Provider 生态** | 1-2 个 embedding 提供者 | 24+ 向量库 / 18+ LLM / 11+ embedder | **mem0 远更强** |
| **存储引擎** | SQLite（事务+版本链） | Qdrant + SQLite history | 各有侧重 |
| **记忆组织** | URI 树形层级 + Gist | 扁平 key-value + 标签过滤 | **MP 更强** |
| **多租户** | domain URI 隔离 | user/agent/app/run 四维 | mem0 更灵活 |

### 📌 能否替代 mem0？

> [!IMPORTANT]
> **不建议将 MP 定位为"mem0 的升级版"——这会偏离项目设计初衷。**
>
> - MP 的设计初衷是 **"AI Agent 长期记忆操作系统"**——通过 MCP 协议为 AI Agent 提供持久化、可检索、可审计的记忆
> - mem0 的定位是 **"通用 AI 记忆中间件"**——为任何 AI 应用提供开箱即用的记忆层
> - 两者在**写入安全、可观测性、治理循环**方面 MP 已胜出；在**事实自动提取、Graph Memory、Provider 覆盖**方面 mem0 更成熟
>
> **建议定位**：MP 是 **"MCP 体系的专业记忆引擎"**，面向 Codex/Claude Code/Gemini CLI 等 MCP 原生工具链。与 mem0 是互补关系，不是替代关系。

### 可从 mem0 借鉴的设计

已有改进中部分与 mem0 思路重合（标记如下），**不增加新改进项**以避免偏离初衷：

| mem0 特性 | 对应改进 | 说明 |
|---|---|---|
| LLM 事实提取 | 改进 6（自动学习触发器）| MP 以 MCP 工具形式实现，不植入 LLM 管线 |
| Reranker 集成 | 现有能力 | MP 已有 |
| 多 Provider | 改进 11（Embedding 可插拔）| 见下方局限性修复 |
| Graph Memory | ⚠️ 不纳入 | 超出 MP 记忆 OS 定位，且需引入图数据库依赖 |

---

## 第二部分：局限性修复（含降级 Fallback 机制）

以下 4 项改进专门针对截图中列出的局限，每项都设计了多档位降级路径。

### 🔴 改进 11（P1）：Embedding 可插拔 + 降级链

**局限**：档位 B 的 Hash Embedding 是 token 级 hash 签名，无法理解语义

**修复方案**：引入可配置的 embedding provider 链，失败时自动降级

#### [MODIFY] [sqlite_client.py](file:///Users/yangjunjie/Desktop/clawanti/Memory-Palace/backend/db/sqlite_client.py)

- 重构 `_fetch_remote_embedding()` 为 `EmbeddingProvider` 抽象
- 降级链：`配置的远程 API` → `备用远程 API` → `本地轻量模型` → `hash embedding（现有档位 B）`
- 环境变量：`EMBEDDING_PROVIDER`（默认 `auto`）、`EMBEDDING_FALLBACK_CHAIN`（默认 `remote,hash`）

**降级 Fallback 矩阵**：

| 档位 | 改进前 | 改进后 | 降级路径 |
|---|---|---|---|
| A | 纯 keyword | 纯 keyword（不变） | — |
| B | keyword + hash | keyword + 远程 embedding（可配） | 远程失败 → hash embedding |
| C/D | keyword + API embedding | keyword + API embedding（不变） | 主 API 失败 → 备用 API → hash |

---

### 🔴 改进 12（P2）：sqlite-vec 向量加速

**局限**：SQLite 不支持 ANN 索引，大规模数据检索效率远不及 Milvus/Faiss

**修复方案**：引入 sqlite-vec 扩展（与 OpenClaw 相同方案），在 SQLite 内实现向量距离查询

#### [MODIFY] [sqlite_client.py](file:///Users/yangjunjie/Desktop/clawanti/Memory-Palace/backend/db/sqlite_client.py)

- 启动时尝试加载 `sqlite-vec` 扩展
- 成功：使用 `vec0` 虚拟表存储/检索向量
- 失败：降级回内存中遍历余弦相似度（现有行为）
- 环境变量：`SQLITE_VEC_ENABLED`（默认 `true`）、`SQLITE_VEC_EXTENSION_PATH`（可选）

**降级 Fallback**：

```
sqlite-vec 可用 → 原生向量索引查询（O(log n)）
       ↓ 扩展加载失败
内存余弦遍历（O(n)，现有行为，记录 degrade_reason）
```

> [!NOTE]
> 这不改变 MP 的"纯 SQLite"定位——sqlite-vec 是 SQLite 扩展而非外部数据库。不引入 Milvus/Faiss 等外部依赖，符合项目"单文件数据库"设计初衷。

---

### 🔴 改进 13（P2）：Write Lane 并发度提升

**局限**：单进程 SQLite 通过 Write Lane 串行化，高并发场景是瓶颈

**修复方案**：WAL 模式 + 读写分离 + 批量写入优化（不引入多进程/多数据库）

#### [MODIFY] [sqlite_client.py](file:///Users/yangjunjie/Desktop/clawanti/Memory-Palace/backend/db/sqlite_client.py)

- 启动时开启 `PRAGMA journal_mode=WAL`（允许并发读）
- 批量索引重建合并为单事务
- 环境变量：`SQLITE_WAL_MODE`（默认 `true`）

#### [MODIFY] [runtime_state.py](file:///Users/yangjunjie/Desktop/clawanti/Memory-Palace/backend/runtime_state.py)

- `WriteLanes` 增加批量合并写入（多个小写入合并为单事务提交）
- 保留 `RUNTIME_WRITE_GLOBAL_CONCURRENCY` 配置

**降级 Fallback**：

```
WAL 模式启用 → 并发读 + 串行写（数倍吞吐提升）
       ↓ WAL 不可用（只读文件系统等）
原有串行模式（记录 degrade_reason）
```

> [!NOTE]
> 不引入多进程/分布式数据库。WAL 模式是 SQLite 原生能力，完全符合"单文件数据库"设计。

---

### 🔴 改进 14（P1）：意图分类 LLM 增强

**局限**：`classify_intent` 用的是关键词评分规则，非模型推理

**修复方案**：保留现有关键词规则为默认，可选 LLM 增强，失败自动降级

#### [MODIFY] [sqlite_client.py](file:///Users/yangjunjie/Desktop/clawanti/Memory-Palace/backend/db/sqlite_client.py)

- `classify_intent()` 增加 LLM 模式：调用配置的 LLM 进行意图分类
- 降级链：`LLM 分类` → `keyword_scoring_v2（现有规则）`
- 环境变量：`INTENT_LLM_ENABLED`（默认 `false`）、`INTENT_LLM_API_BASE`、`INTENT_LLM_MODEL`
- 复用现有 Write Guard 的 LLM 配置机制

**降级 Fallback**：

```
INTENT_LLM_ENABLED=true → LLM 意图分类（更准确）
       ↓ API 超时/失败
keyword_scoring_v2（现有规则，记录 degrade_reason）
       ↓（始终可用，无进一步降级）
```

---

## 第三部分：完整 14 项改进一览

| P | # | 改进 | 来源 | 工作量 | 降级保障 |
|---|---|---|---|---|---|
| **P0** | 1 | 索引自动生成 | 🔵 CC | ~2天 | 生成失败不阻塞 compact |
| **P0** | 2 | 审计 URI | 🔵 CC | ~1天 | 部分数据缺失时仍返回可用子集 |
| **P0** | 7 | MMR 去重 | 🟠 OC | ~1天 | 默认关闭，可配置开启 |
| **P1** | 3 | 作用域规则 | 🔵 CC | ~2天 | 无 scope 的记忆行为不变 |
| **P1** | 4 | 层级继承 | 🔵 CC | ~2天 | 默认关闭，显式开启 |
| **P1** | 8 | 搜索权重可配 | 🟠 OC | ~1天 | 默认值与现有行为一致 |
| **P1** | 9 | 自动 flush | 🟣 融合 | ~2天 | 仅返回提醒，不强制操作 |
| **P1** | 11 | Embedding 可插拔 | 🔴 局限 | ~2天 | 远程→hash 三级降级 |
| **P1** | 14 | 意图分类 LLM | 🔴 局限 | ~2天 | LLM→关键词规则降级 |
| **P2** | 5 | 外部导入 | 🔵 CC | ~2天 | 引用不可达时显示占位 |
| **P2** | 6 | 自动学习 | 🔵 CC | ~3天 | 提供 MCP 工具，不植入 LLM 管线 |
| **P2** | 10 | 嵌入缓存 | 🟠 OC | ~1天 | 缓存未命中退回实时计算 |
| **P2** | 12 | sqlite-vec 加速 | 🔴 局限 | ~2天 | 扩展不可用退回遍历 |
| **P2** | 13 | Write Lane 优化 | 🔴 局限 | ~1天 | WAL 不可用退回串行 |

> 总计约 **24 人天**，建议按 P0（~4天）→ P1（~11天）→ P2（~9天）分三批。

### 完整检索管线 Fallback 矩阵

改进后完整的检索流程：

```
查询 → 意图分类(#14) → 策略模板(#8权重可配) → 检索执行 → MMR去重(#7) → 返回
                                                    ↓
                              ┌──────────────┬──────────────┬──────────────┐
                              │   keyword    │   semantic   │    hybrid    │
                              │  (BM25/FTS)  │  (向量检索)   │ (keyword+vec)│
                              └──────────────┴──────────────┴──────────────┘
```

**按检索模式的降级路径**：

#### `keyword` 模式（始终可用，最终兜底）

```
SQLite FTS5 → 结果
   ↓ FTS 不可用（极端情况）
LIKE 模糊匹配（记录 degrade_reason）
```

不受 embedding 改进影响。改进 #7 MMR / #8 权重对此模式不适用。

#### `semantic` 模式

```
意图分类(#14 LLM → 关键词规则)
   ↓
Embedding 获取(#11 可插拔降级链):
   远程 API → 备用 API → 本地模型 → hash embedding
   ↓
向量检索(#12 sqlite-vec → 内存余弦遍历)
   ↓
缓存层(#10 命中 → 跳过 embedding 计算)
   ↓
MMR 去重(#7 开启 → 多样性过滤; 关闭 → 跳过)
   ↓ embedding 全链路失败
⚠️ 自动降级到 keyword 模式（记录 degrade_reason）
```

#### `hybrid` 模式（默认推荐）

```
意图分类(#14 LLM → 关键词规则)
   ↓
策略模板 → 权重(#8): vectorWeight / textWeight 可配
   ↓
并行执行:
   ├─ keyword 分支: FTS5 BM25（始终成功）
   └─ semantic 分支: embedding(#11) → 向量检索(#12) → 缓存(#10)
   ↓
加权合并: finalScore = textWeight × textScore + vectorWeight × vectorScore
   ↓ semantic 分支失败
⚠️ 退化为纯 keyword（vectorWeight 归零，记录 degrade_reason）
   ↓
MMR 去重(#7) → Reranker(现有) → 返回
```

**按档位的改进后完整 Fallback 矩阵**：

| 档位 | keyword 模式 | semantic 模式 | hybrid 模式 |
|---|---|---|---|
| **A** | FTS5（不变） | ❌ 不支持→降级 keyword | ❌ 不支持→降级 keyword |
| **B** | FTS5（不变） | 远程 embedding(#11)→hash→降级 keyword | FTS5 + 远程 embedding(#11)→hash→纯keyword |
| **B+** | FTS5 + sqlite-vec(#12) | 远程 embedding(#11)+vec加速→hash→降级 keyword | FTS5 + embedding(#11)+vec(#12)→hash→纯keyword |
| **C/D** | FTS5（不变） | API embedding+vec(#12)+reranker→hash→降级 keyword | FTS5 + API embedding+vec(#12)+reranker→hash→纯keyword |

> **B+ 是改进后新增的中间档位**：比 B 多了 sqlite-vec 加速和远程 embedding 可配，但不需要 reranker API。

**各改进项对检索模式的影响**：

| 改进 | keyword | semantic | hybrid |
|---|---|---|---|
| #7 MMR 去重 | — | ✅ 减少冗余 | ✅ 减少冗余 |
| #8 权重可配 | — | — | ✅ 调节 text/vec 比重 |
| #10 嵌入缓存 | — | ✅ 加速 | ✅ 加速 |
| #11 Embedding 可插拔 | — | ✅ 增强语义质量+降级 | ✅ 增强语义质量+降级 |
| #12 sqlite-vec | — | ✅ 向量检索加速 | ✅ 向量检索加速 |
| #14 意图 LLM | ✅ 更准确路由 | ✅ 更准确路由 | ✅ 更准确路由 |

### 降级 Fallback 总体设计原则

> [!IMPORTANT]
> **所有改进遵循 MP 现有的"多档位可用"原则**：
>
> 1. **默认不改变现有行为**——新特性默认关闭或使用与现有一致的默认值
> 2. **每项增强都有降级路径**——环境变量控制，失败时自动降级到前一档位
> 3. **降级可见**——所有降级通过 `degrade_reasons` 字段报告，可在仪表盘观测
> 4. **不引入新外部必需依赖**——sqlite-vec 是可选扩展，LLM 意图分类可关闭
> 5. **档位 A（纯 keyword）始终可用**——作为最终兜底
> 6. **semantic/hybrid 失败始终降级到 keyword**——不会出现检索完全不可用的情况

---

## 验证计划

### 降级测试（关键新增）

| 场景 | 验证方法 |
|---|---|
| Embedding API 不可达 | 断开网络，确认降级到 hash |
| sqlite-vec 扩展缺失 | 不安装扩展，确认降级到遍历 |
| 意图 LLM 超时 | mock 超时，确认降级到 keyword_scoring |
| WAL 模式不可用 | 只读文件系统，确认串行模式 |

### 回归 + 新增测试

```bash
python -m pytest backend/tests/ -v  # 现有回归
```

新增测试文件覆盖改进 1-14（每项一个测试文件）。
