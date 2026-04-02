# Memory Palace — Cortex-Inspired Improvements Design

**Date:** 2026-04-02
**Status:** Approved
**Approach:** Layered (层叠式) — incremental additions on existing architecture

## Background

Comparison with [rikouu/cortex](https://github.com/rikouu/cortex) revealed Memory Palace excels at structured addressing (URI tree, aliases, snapshot/rollback) but lacks lifecycle management, automatic extraction, and feedback loops. This design adds those capabilities while preserving existing strengths.

## Scope

Full improvement (Option C):
1. Infrastructure fix (sqlite-vec + reranker)
2. Memory lifecycle (working → core → archive → compressed core)
3. Dual-channel extraction (regex fast + LLM deep)
4. Feedback loop
5. Query expansion

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Layered (层叠式) | Follows existing mcp_server → sqlite_client → maintenance separation; each feature independently toggleable |
| Extraction trigger | Dual-channel (Cortex SIEVE) | Fast regex for explicit signals (0ms), LLM for deep extraction (async) |
| LLM endpoint | Reuse ROUTER_API_BASE | No new infra; shared with gist/write-guard |
| Lifecycle automation | Fully automatic (cron) | No human intervention; cron every 6h |
| Vitality integration | Fusion | vitality_score preserved as lifecycle input signal, not replaced |

---

## Module 1: DB Schema Extension

Migration: `0004_add_lifecycle_fields.sql`

### memories table — new columns

| Column | Type | Default | Description |
|---|---|---|---|
| `layer` | TEXT | `'core'` | `working` / `core` / `archive` |
| `importance` | FLOAT | `0.5` | 0.0–1.0, set by extraction or manual |
| `access_count` | INTEGER | `0` | Incremented on search hit |
| `last_accessed_at` | DATETIME | NULL | Updated on search hit |
| `category` | TEXT | NULL | One of 18 categories (see below) |
| `source` | TEXT | `'manual'` | `manual` / `extracted` / `compressed` |
| `confidence` | FLOAT | `1.0` | Extraction confidence; regex=1.0, LLM-assigned otherwise |
| `expires_at` | DATETIME | NULL | Working layer: created_at + 48h |

### New table: memory_feedback

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `memory_id` | INTEGER FK | References memories.id |
| `signal` | TEXT | `helpful` / `outdated` / `wrong` |
| `reason` | TEXT | Optional explanation |
| `created_at` | DATETIME | Timestamp |

### New table: lifecycle_log

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `phase` | TEXT | Phase name (e.g. `promote`, `archive`, `compress`) |
| `details` | TEXT (JSON) | Phase execution summary |
| `created_at` | DATETIME | Timestamp |

### Migration strategy

All existing memories get `layer='core'`, `source='manual'`, `importance=0.5`, `confidence=1.0`. No data loss, fully backward compatible.

### 18 Memory Categories

**User-owned:** identity, preference, decision, constraint, correction, fact, goal, skill, entity, todo, relationship, insight, project_state

**Agent self-learning:** agent_self_improvement, agent_user_habit, agent_relationship, agent_persona

Note: `extraction` was removed as a category — it overlaps with `source='extracted'` and adds no distinct semantic value.

### Attribution constraint

- User message → user-owned categories only
- Assistant message → `agent_*` categories only

---

## Module 2: Dual-Channel Extraction Engine

New file: `backend/extraction/engine.py`

### MCP Tool

```
ingest_conversation(user_message, assistant_message, agent_id?) → IngestResult
```

Returns: `{ok, fast_extracted: [...], deep_extracted: [...], skipped_reason?}`

### Fast Channel (regex, 0ms)

Predefined patterns → write directly to `layer='core'`, `confidence=1.0`:

| Pattern | Category | Examples |
|---|---|---|
| `我是/I am/I'm a` | `identity` | "我是数据科学家" |
| `不要/别/don't/never` | `constraint` | "不要用 rm" |
| `记住/remember` | `preference` | "记住我喜欢简洁回复" |
| `纠正/其实/actually` | `correction` | "其实那个 API 已经废弃了" |
| `偏好/prefer/习惯` | `preference` | "我习惯用 vim" |

Patterns stored in `backend/extraction/patterns.json`, hot-reloadable.

### Deep Channel (LLM, 200-400ms, async)

- Uses `ROUTER_API_BASE` for LLM calls
- Prompt instructs: extract long-term-worthy facts, output `{content, category, importance, confidence}`
- Enforces attribution constraint
- Token budget proportional to message length
- Writes to `layer='working'`, `expires_at = now + 48h`

### Deduplication

- Write-time: MD5 hash of `agent_id|||user_msg|||assistant_msg` with 10-min window → skip
- Semantic dedup deferred to lifecycle engine (promote phase)

### Degradation

- LLM unavailable → fast channel only
- Fast channel no match → silent skip, no error

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EXTRACTION_ENABLED` | `true` | Master switch |
| `EXTRACTION_FAST_ENABLED` | `true` | Fast channel switch |
| `EXTRACTION_DEEP_ENABLED` | `true` | Deep channel switch |
| `EXTRACTION_DEDUP_WINDOW_SEC` | `600` | MD5 dedup window |
| `EXTRACTION_DEEP_TIMEOUT_SEC` | `5` | LLM timeout |

---

## Module 3: Lifecycle Engine

New file: `backend/lifecycle/engine.py`

Cron-scheduled (default every 6 hours). Six sequential phases:

### Phase 1: Clean expired working

- Condition: `layer='working' AND expires_at < now`
- Action: Delete (working is temporary; expiry means not worth keeping)

### Phase 2: Promote working → core

- Condition: `layer='working' AND expires_at >= now`
- Score: `importance * 0.3 + access_factor * 0.4 + vitality_factor * 0.3`
  - `access_factor = min(access_count / 5, 1.0)`
  - `vitality_factor = vitality_score`
- Threshold: `score >= 0.4` → promote to core, clear `expires_at`
- **Fast track:** `category in (identity, constraint) AND confidence >= 0.3` → immediate promotion

### Phase 3: Core deduplication

- Vector similarity comparison among core memories (requires sqlite-vec)
- Similarity > 0.92 → merge (keep higher importance, union content)
- sqlite-vec disabled → skip phase

### Phase 4: Decay core → archive

- Uses existing vitality decay pipeline as input
- Condition: `layer='core' AND vitality_score < 0.2 AND last_accessed_at < now - 90d`
- Action: set `layer='archive'`, `expires_at = now + 90d`

### Phase 5: Compress archive → core summary

- Condition: `layer='archive' AND expires_at < now`
- Batch same-category expired archives, LLM summarize into one core memory
- New memory: `layer='core'`, `source='compressed'`, `importance=0.3`
- Original archives: `deprecated=True` (reuse existing version chain)
- LLM unavailable → skip, archives retained for next cycle

### Phase 6: Feedback adjustment

- Read `memory_feedback`, for memories with ≥3 feedbacks:
  - helpful > 70% → `importance += 0.1` (cap 1.0)
  - wrong/outdated > 50% → `importance -= 0.15` (floor 0.0)
- Per-category stats: categories with >30% negative feedback → new extractions in that category get `importance` reduced by 15%

### Audit

Each phase logs to `lifecycle_log` table:
```json
{"phase": "promote", "promoted": 3, "skipped": 12, "timestamp": "..."}
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LIFECYCLE_ENABLED` | `true` | Master switch |
| `LIFECYCLE_CRON_EXPRESSION` | `0 */6 * * *` | Execution frequency |
| `LIFECYCLE_PROMOTE_THRESHOLD` | `0.4` | Promotion score threshold |
| `LIFECYCLE_ARCHIVE_VITALITY_THRESHOLD` | `0.2` | Vitality threshold for archiving |
| `LIFECYCLE_ARCHIVE_STALE_DAYS` | `90` | Days without access before archiving |
| `LIFECYCLE_ARCHIVE_RETENTION_DAYS` | `90` | Archive retention before compression |
| `LIFECYCLE_DEDUP_SIMILARITY_THRESHOLD` | `0.92` | Dedup similarity threshold |

---

## Module 4: Feedback Loop + Query Expansion

### 4A: Feedback Loop

**Search result enrichment:** Each result includes `feedback_hint` with the tool call template.

**New MCP tool:**
```
memory_feedback(memory_id, signal, reason?) → {ok, message}
```

**Access tracking:** Search hits auto-increment `access_count` and update `last_accessed_at`.

### 4B: Query Expansion

Inserted in search pipeline before embedding (hybrid/semantic modes only).

| Query length | Expansion | LLM temperature |
|---|---|---|
| ≤ 15 chars | 4-6 synonym keywords | 0.2 |
| > 15 chars | Up to 3 rephrased variants | 0.4 |

**CJK awareness:** Chinese queries prompt for related English keywords and vice versa.

**Execution:**
1. Original query + expanded variants → batch embedding (single API call)
2. Independent retrieval per variant
3. Multi-query hit boost: `score *= (1 + 0.1 * ln(hit_count))`
4. Merge, dedup, rerank, top-k

**Degradation:** LLM unavailable → original query only, no error.

| Variable | Default | Description |
|---|---|---|
| `QUERY_EXPANSION_ENABLED` | `true` | Switch |
| `QUERY_EXPANSION_TIMEOUT_SEC` | `3` | LLM timeout |
| `QUERY_EXPANSION_MIN_QUERY_LEN` | `2` | Minimum query length to expand |

### 4C: Infrastructure Fix (Prerequisite)

1. **Enable sqlite-vec** — diagnose why `sqlite_vec_enabled: false`, load extension, verify KNN works
2. **Fix reranker timeout** — check llama-server at `:11436`, adjust `RETRIEVAL_REMOTE_TIMEOUT_SEC`

These are prerequisites for hybrid search, dedup, and query expansion.

---

## Implementation Order

```
Phase 0: Infrastructure fix (sqlite-vec + reranker)
    ↓
Phase 1: DB migration (0004)
    ↓
Phase 2: Extraction engine (fast + deep channels)
    ↓
Phase 3: Lifecycle engine (6 phases)
    ↓
Phase 4: Feedback loop + query expansion
    ↓
Phase 5: Integration test + tuning
```

Each phase is independently deployable and feature-flagged via environment variables.
