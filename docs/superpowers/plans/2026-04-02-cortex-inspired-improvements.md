# Cortex-Inspired Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Memory Palace from passive storage to an active learning system with memory lifecycle management, automatic extraction, feedback loops, and query expansion.

**Architecture:** Layered additions on existing `mcp_server.py` → `sqlite_client.py` → `maintenance.py` stack. Each feature independently toggleable via env vars. New modules: `backend/extraction/` (dual-channel extractor), `backend/lifecycle/` (6-phase lifecycle engine). Existing vitality fused as lifecycle input.

**Tech Stack:** Python 3.12+, SQLAlchemy async, aiosqlite, FastMCP, httpx (LLM calls), pytest

**Spec:** `docs/superpowers/specs/2026-04-02-cortex-inspired-improvements-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `backend/db/migrations/0004_add_lifecycle_fields.sql` | New columns + tables |
| Create | `backend/db/migrations/0004_add_lifecycle_fields.rollback.sql` | Rollback |
| Modify | `backend/db/sqlite_client.py:264-298` | Add columns to `Memory` ORM |
| Create | `backend/db/models_lifecycle.py` | `MemoryFeedback`, `LifecycleLog` ORM |
| Create | `backend/extraction/__init__.py` | Package init |
| Create | `backend/extraction/patterns.json` | Fast channel regex config |
| Create | `backend/extraction/fast_channel.py` | Regex extraction |
| Create | `backend/extraction/deep_channel.py` | LLM extraction |
| Create | `backend/extraction/engine.py` | Dual-channel orchestrator + dedup |
| Create | `backend/lifecycle/__init__.py` | Package init |
| Create | `backend/lifecycle/engine.py` | 6-phase lifecycle engine |
| Create | `backend/lifecycle/scheduler.py` | Cron scheduling |
| Modify | `backend/mcp_server.py` (search_memory ~L4342) | Access tracking + feedback_hint |
| Modify | `backend/mcp_server.py` (end of file) | New MCP tools: `ingest_conversation`, `memory_feedback` |
| Create | `backend/extraction/query_expansion.py` | Query expansion layer |
| Modify | `backend/runtime_state.py` | Lifecycle scheduler in runtime |
| Modify | `backend/api/maintenance.py` | Lifecycle trigger endpoints |
| Create | `backend/tests/test_lifecycle_migration.py` | Migration tests |
| Create | `backend/tests/test_extraction_fast.py` | Fast channel tests |
| Create | `backend/tests/test_extraction_deep.py` | Deep channel tests |
| Create | `backend/tests/test_extraction_engine.py` | Orchestrator tests |
| Create | `backend/tests/test_lifecycle_engine.py` | Lifecycle tests |
| Create | `backend/tests/test_feedback.py` | Feedback tool tests |
| Create | `backend/tests/test_query_expansion.py` | Query expansion tests |

---

## Task 0: Infrastructure Fix — sqlite-vec + Reranker

**Files:**
- Modify: `.env` (on deployed instance)
- Investigate: `backend/db/sqlite_client.py` (sqlite-vec loading logic)
- Investigate: llama-server at `:11436` (reranker)

- [ ] **Step 1: Diagnose sqlite-vec** — check why `sqlite_vec_enabled: false`:
  - `GET http://192.168.5.191:8000/health` → check `sqlite_vec_enabled`, `sqlite_vec_knn_ready`
  - Grep for `sqlite_vec` / `load_extension` in `sqlite_client.py` to find the loading logic
  - Common causes: extension `.so`/`.dylib` not found, `RETRIEVAL_EMBEDDING_BACKEND` set to `none`/`hash`
  - Fix: ensure `sqlite-vec` Python package installed, `RETRIEVAL_EMBEDDING_BACKEND` set to a real provider (e.g. the Qwen3-Embedding at `:11435`)

- [ ] **Step 2: Configure embedding backend** — update `.env`:
  - `RETRIEVAL_EMBEDDING_BACKEND=api`
  - `RETRIEVAL_EMBEDDING_API_BASE=http://127.0.0.1:11435` (Qwen3-Embedding-0.6B)
  - `RETRIEVAL_EMBEDDING_MODEL=qwen3-embedding-0.6b`
  - `RETRIEVAL_EMBEDDING_DIM=1024` (check actual dim for Qwen3-Embedding)
  - `SEARCH_DEFAULT_MODE=hybrid`

- [ ] **Step 3: Diagnose reranker timeout** — check llama-server at `:11436`:
  - `curl http://127.0.0.1:11436/health` on the server
  - If down: restart via launchd or check process
  - If slow: increase `RETRIEVAL_REMOTE_TIMEOUT_SEC` (current default 8s, try 15s)
  - Configure: `RETRIEVAL_RERANKER_ENABLED=true`, `RETRIEVAL_RERANKER_API_BASE=http://127.0.0.1:11436`

- [ ] **Step 4: Verify** — restart Memory Palace, run search in hybrid mode, confirm no `degraded` flags for vec or reranker

- [ ] **Step 5: Commit .env changes** (if any config file changes, not secrets)

---

## Task 1: DB Migration — Lifecycle Fields

**Files:**
- Create: `backend/db/migrations/0004_add_lifecycle_fields.sql`
- Create: `backend/db/migrations/0004_add_lifecycle_fields.rollback.sql`
- Modify: `backend/db/sqlite_client.py:264-298` (Memory ORM)
- Create: `backend/db/models_lifecycle.py`
- Create: `backend/tests/test_lifecycle_migration.py`

- [ ] **Step 1: Write test** — `test_lifecycle_migration.py` with 3 test cases:
  - `test_migration_adds_lifecycle_columns`: create memory, verify `layer='core'`, `importance=0.5`, `source='manual'`, `confidence=1.0`, `category=None`, `expires_at=None`
  - `test_memory_feedback_table_exists`: select from `memory_feedback`, expect empty list (no error)
  - `test_lifecycle_log_table_exists`: select from `lifecycle_log`, expect empty list
  - Follow existing test pattern from `test_week6_vitality_cleanup.py`: `SQLiteClient(_sqlite_url(db_path))`, `await client.init_db()`

- [ ] **Step 2: Run test, verify FAIL** — `Memory` has no `layer` attribute

- [ ] **Step 3: Write migration SQL** — `0004_add_lifecycle_fields.sql`:
  - `ALTER TABLE memories ADD COLUMN layer TEXT NOT NULL DEFAULT 'core'`
  - `ALTER TABLE memories ADD COLUMN importance REAL NOT NULL DEFAULT 0.5`
  - `ALTER TABLE memories ADD COLUMN category TEXT`
  - `ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'`
  - `ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0`
  - `ALTER TABLE memories ADD COLUMN expires_at DATETIME`
  - Indexes: `idx_memories_layer`, `idx_memories_layer_expires`, `idx_memories_category`
  - `CREATE TABLE memory_feedback` (id, memory_id FK, signal CHECK IN ('helpful','outdated','wrong'), reason, created_at)
  - `CREATE TABLE lifecycle_log` (id, phase, details TEXT/JSON, created_at)
  - Rollback: drop indexes, drop tables, drop columns (SQLite ≥3.35)

- [ ] **Step 4: Add columns to Memory ORM** — Edit `sqlite_client.py` class `Memory(Base)`, add after `access_count` (L293):
  - `layer = Column(Text, default="core", server_default=text("'core'"), nullable=False)`
  - `importance = Column(Float, default=0.5, server_default=text("0.5"), nullable=False)`
  - `category = Column(Text, nullable=True)`
  - `source = Column(Text, default="manual", server_default=text("'manual'"), nullable=False)`
  - `confidence = Column(Float, default=1.0, server_default=text("1.0"), nullable=False)`
  - `expires_at = Column(DateTime, nullable=True)`

- [ ] **Step 5: Create `models_lifecycle.py`** — `MemoryFeedback` and `LifecycleLog` classes using `Base` from `sqlite_client`

- [ ] **Step 6: Run test, verify PASS**

- [ ] **Step 7: Commit** — `feat: add lifecycle fields migration (0004) and ORM models`

---

## Task 2: Fast Channel Extraction

**Files:**
- Create: `backend/extraction/__init__.py`, `backend/extraction/patterns.json`, `backend/extraction/fast_channel.py`
- Create: `backend/tests/test_extraction_fast.py`

- [ ] **Step 1: Write test** — `test_extraction_fast.py`:
  - `test_identity_chinese`: `extract_fast("我是一名数据科学家", role="user")` → category=identity, confidence=1.0
  - `test_constraint_english`: `extract_fast("Don't ever use rm", role="user")` → category=constraint
  - `test_preference_chinese`: `extract_fast("记住我喜欢简洁回复", role="user")` → category=preference
  - `test_correction`: `extract_fast("其实那个API废弃了", role="user")` → category=correction
  - `test_no_match`: `extract_fast("今天天气不错", role="user")` → empty list
  - `test_assistant_produces_agent_category`: assistant messages → only `agent_*` categories
  - `test_multiple_matches`: `extract_fast("我是工程师，不要用JS", role="user")` → identity + constraint

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Create `extraction/__init__.py`** — empty package init

- [ ] **Step 4: Create `patterns.json`** — JSON config with:
  - `user_patterns`: identity (`我是/I am/I'm a`), constraint (`不要/别/don't/never`), preference (`记住/remember/偏好`), correction (`其实/actually`)
  - `assistant_patterns`: agent_user_habit (`I noticed you/你似乎`)
  - Each entry: `{category, patterns: [regex...], extract_group: 0|1}`

- [ ] **Step 5: Implement `fast_channel.py`** — `extract_fast(message, role) -> List[Dict]`:
  - Load patterns from JSON with hot-reload (check mtime)
  - Select `user_patterns` or `assistant_patterns` based on role
  - Match regex, avoid overlapping spans
  - Return `{content, category, confidence: 1.0, source: "fast_channel"}`

- [ ] **Step 6: Run test, verify PASS**

- [ ] **Step 7: Commit** — `feat: add fast channel regex extraction`

---

## Task 3: Deep Channel Extraction

**Files:**
- Create: `backend/extraction/deep_channel.py`
- Create: `backend/tests/test_extraction_deep.py`

- [ ] **Step 1: Write test** — `test_extraction_deep.py` (mock LLM via `unittest.mock.patch`):
  - `test_returns_structured_results`: mock `_call_llm` returning valid JSON → parse results
  - `test_enforces_attribution`: assistant-attributed memory with user category → remapped to `agent_user_habit`
  - `test_llm_timeout_returns_empty`: mock raises `TimeoutError` → empty list
  - `test_invalid_json_returns_empty`: mock returns garbage → empty list
  - `test_valid_categories`: verify USER_CATEGORIES has ≥10, AGENT_CATEGORIES has ≥3

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Implement `deep_channel.py`**:
  - Constants: `USER_CATEGORIES` (13), `AGENT_CATEGORIES` (4), `VALID_CATEGORIES` = union
  - `_call_llm(system_prompt, user_prompt) -> str`: httpx POST to `ROUTER_API_BASE/v1/chat/completions`, timeout from `EXTRACTION_DEEP_TIMEOUT_SEC` (default 5s)
  - `_build_user_prompt(user_msg, assistant_msg) -> str`: token budget = `min(5, max(1, total_len // 200))` max memories
  - System prompt: instructs extraction with attribution constraint, JSON output format
  - `extract_deep(user_message, assistant_message) -> List[Dict]`:
    1. Call LLM
    2. Parse JSON (with trailing comma / newline repair)
    3. Validate categories, enforce attribution (remap user-category on assistant → `agent_user_habit`)
    4. Clamp importance/confidence to [0,1]
    5. Return `{content, category, importance, confidence, source: "deep_channel", _attributed_to}`
    6. On any error → return `[]`

- [ ] **Step 4: Run test, verify PASS**

- [ ] **Step 5: Commit** — `feat: add deep channel LLM extraction`

---

## Task 4: Extraction Engine (Orchestrator + Dedup)

**Files:**
- Create: `backend/extraction/engine.py`
- Create: `backend/tests/test_extraction_engine.py`

- [ ] **Step 1: Write test** — `test_extraction_engine.py`:
  - `test_ingest_runs_both_channels`: mock both channels, verify both called, results merged
  - `test_dedup_skips_duplicate_within_window`: same message twice within 10min → second returns `skipped_reason`
  - `test_dedup_allows_after_window`: same message after window expires → processed
  - `test_fast_only_when_deep_disabled`: set `EXTRACTION_DEEP_ENABLED=false` → only fast results
  - `test_disabled_returns_early`: set `EXTRACTION_ENABLED=false` → returns `{ok: false, skipped_reason: "disabled"}`
  - `test_writes_to_db`: verify extracted memories written to DB with correct `layer`/`expires_at`

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Implement `engine.py`**:
  - `_dedup_cache: Dict[str, float]` — MD5 hash → timestamp, window from `EXTRACTION_DEDUP_WINDOW_SEC` (600)
  - `_compute_dedup_key(agent_id, user_msg, assistant_msg) -> str`: MD5 of `agent_id|||user_msg|||assistant_msg`
  - `async def ingest_conversation(user_message, assistant_message, agent_id=None) -> Dict`:
    1. Check env flags (`EXTRACTION_ENABLED`, `EXTRACTION_FAST_ENABLED`, `EXTRACTION_DEEP_ENABLED`)
    2. Dedup check
    3. Run fast channel (sync, immediate)
    4. Run deep channel (async, with timeout)
    5. Write fast results to DB: `layer='core'`, `confidence=1.0` (via `sqlite_client.create_memory`)
    6. Write deep results to DB: `layer='working'`, `expires_at=now+48h`
    7. Return `{ok, fast_extracted, deep_extracted, skipped_reason?}`

- [ ] **Step 4: Run test, verify PASS**

- [ ] **Step 5: Commit** — `feat: add extraction engine with dedup`

---

## Task 5: Register MCP Tools (ingest_conversation + memory_feedback)

**Files:**
- Modify: `backend/mcp_server.py` (end of file, after `compact_context`)
- Create: `backend/tests/test_feedback.py`

- [ ] **Step 1: Write test** — `test_feedback.py`:
  - `test_memory_feedback_writes_to_db`: create memory, call feedback, verify row in `memory_feedback`
  - `test_memory_feedback_invalid_signal`: signal="invalid" → error response
  - `test_memory_feedback_missing_memory`: nonexistent memory_id → error

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Add `ingest_conversation` MCP tool** — at end of `mcp_server.py`:
  - `@mcp.tool()` decorator
  - Signature: `async def ingest_conversation(user_message: str, assistant_message: str, agent_id: Optional[str] = None) -> str`
  - Delegate to `extraction.engine.ingest_conversation()`
  - Return JSON result

- [ ] **Step 4: Add `memory_feedback` MCP tool**:
  - `@mcp.tool()` decorator
  - Signature: `async def memory_feedback(memory_id: int, signal: str, reason: Optional[str] = None) -> str`
  - Validate signal in ('helpful', 'outdated', 'wrong')
  - Validate memory exists
  - Insert into `memory_feedback` table
  - Return `{ok: true}`

- [ ] **Step 5: Run test, verify PASS**

- [ ] **Step 6: Commit** — `feat: register ingest_conversation and memory_feedback MCP tools`

---

## Task 6: Access Tracking + Feedback Hint in Search

**Files:**
- Modify: `backend/mcp_server.py:4758-4783` (search result post-processing)
- Modify: `backend/db/sqlite_client.py` (access tracking in search)

- [ ] **Step 1: Write test** — add to `test_feedback.py`:
  - `test_search_results_include_feedback_hint`: search, verify each result has `feedback_hint` string
  - `test_search_increments_access_count`: search hit → memory's `access_count` incremented, `last_accessed_at` updated
  - Note: `access_count`/`last_accessed_at` tracking may already exist (check `test_week6_vitality_cleanup.py:L19-46`). If so, verify it still works with new fields.

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Add `feedback_hint` to search results** — in `mcp_server.py` search_memory, after building `final_results` (~L4662), inject into each result:
  ```python
  for item in final_results:
      mid = item.get("memory_id")
      if mid is not None:
          item["feedback_hint"] = f"memory_feedback(memory_id={mid}, signal='helpful|outdated|wrong')"
  ```

- [ ] **Step 4: Verify access tracking works with new fields** — existing `search_advanced` in `sqlite_client.py` already updates `access_count` and `last_accessed_at`. Verify this still works after ORM changes from Task 1.

- [ ] **Step 5: Run test, verify PASS**

- [ ] **Step 6: Commit** — `feat: add feedback_hint to search results`

---

## Task 7: Lifecycle Engine — Phases 1-3

**Files:**
- Create: `backend/lifecycle/__init__.py`
- Create: `backend/lifecycle/engine.py`
- Create: `backend/tests/test_lifecycle_engine.py`

- [ ] **Step 1: Write test** — `test_lifecycle_engine.py` part 1:
  - `test_phase1_cleans_expired_working`: create working memory with expired `expires_at` → after run, memory deleted
  - `test_phase1_keeps_unexpired_working`: working memory with future `expires_at` → still exists
  - `test_phase2_promotes_high_score`: working memory with high importance + access → promoted to core
  - `test_phase2_fast_track_identity`: identity category + confidence≥0.3 → immediate promotion
  - `test_phase2_skips_low_score`: working memory with 0 access, low importance → stays working
  - `test_phase3_dedup_merges_similar`: two core memories with identical content → merged (keep higher importance)
  - `test_phase3_skips_when_no_vec`: mock sqlite-vec unavailable → phase skipped gracefully

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Implement `lifecycle/__init__.py`** — empty

- [ ] **Step 4: Implement phases 1-3 in `lifecycle/engine.py`**:
  - `class LifecycleEngine`:
    - `__init__(self, client: SQLiteClient)` — store client ref
    - `async def run(self) -> Dict` — run all phases sequentially, return audit summary
    - `async def _phase1_clean_expired(self) -> Dict` — query `layer='working' AND expires_at < now`, delete, log count
    - `async def _phase2_promote(self) -> Dict` — query unexpired working, compute score = `importance*0.3 + min(access_count/5,1.0)*0.4 + vitality_score*0.3`, promote if ≥ threshold (env `LIFECYCLE_PROMOTE_THRESHOLD`, default 0.4). Fast track: category in (identity, constraint) and confidence ≥ 0.3.
    - `async def _phase3_dedup(self) -> Dict` — if sqlite-vec available, compare core memory vectors, merge if similarity > `LIFECYCLE_DEDUP_SIMILARITY_THRESHOLD` (0.92). If not available, skip with `{"skipped": "sqlite_vec_unavailable"}`.
    - `_log_phase(phase, details)` — insert into `lifecycle_log`

- [ ] **Step 5: Run test, verify PASS**

- [ ] **Step 6: Commit** — `feat: lifecycle engine phases 1-3 (clean, promote, dedup)`

---

## Task 8: Lifecycle Engine — Phases 4-6

**Files:**
- Modify: `backend/lifecycle/engine.py`
- Modify: `backend/tests/test_lifecycle_engine.py`

- [ ] **Step 1: Write test** — add to `test_lifecycle_engine.py`:
  - `test_phase4_archives_stale_core`: core memory with vitality < 0.2 and last_accessed > 90d ago → archived
  - `test_phase4_keeps_healthy_core`: core with good vitality → stays core
  - `test_phase5_compresses_expired_archive`: archive with expired `expires_at` → LLM summarize (mock) → new core `source='compressed'`, old deprecated
  - `test_phase5_skips_when_llm_unavailable`: LLM mock raises → archives retained
  - `test_phase6_adjusts_importance_up`: 3+ helpful feedbacks → importance += 0.1
  - `test_phase6_adjusts_importance_down`: 3+ wrong/outdated feedbacks → importance -= 0.15
  - `test_phase6_caps_importance`: importance already 1.0 + helpful → stays 1.0

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Implement phases 4-6**:
  - `_phase4_archive()`: query `layer='core' AND vitality_score < LIFECYCLE_ARCHIVE_VITALITY_THRESHOLD AND last_accessed_at < now - LIFECYCLE_ARCHIVE_STALE_DAYS`. Set `layer='archive'`, `expires_at=now + LIFECYCLE_ARCHIVE_RETENTION_DAYS`.
  - `_phase5_compress()`: query `layer='archive' AND expires_at < now`. Group by category. Call LLM to summarize each group. Create new memory: `layer='core'`, `source='compressed'`, `importance=0.3`. Mark originals `deprecated=True`. LLM failure → skip.
  - `_phase6_feedback_adjust()`: query `memory_feedback` grouped by `memory_id`, for memories with ≥3 feedbacks: helpful>70% → importance+0.1 (cap 1.0), wrong/outdated>50% → importance-0.15 (floor 0.0). Also compute per-category negative rate for extraction penalty metadata.

- [ ] **Step 4: Run test, verify PASS**

- [ ] **Step 5: Commit** — `feat: lifecycle engine phases 4-6 (archive, compress, feedback)`

---

## Task 9: Lifecycle Scheduler + Runtime Integration

**Files:**
- Create: `backend/lifecycle/scheduler.py`
- Modify: `backend/runtime_state.py`
- Modify: `backend/api/maintenance.py`

- [ ] **Step 1: Write test** — add to `test_lifecycle_engine.py`:
  - `test_scheduler_respects_enabled_flag`: `LIFECYCLE_ENABLED=false` → scheduler does not run
  - `test_full_lifecycle_run_audit_log`: run full lifecycle, verify `lifecycle_log` has entries for each phase

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Implement `scheduler.py`**:
  - Use `asyncio` background task (following existing `VitalityDecayCoordinator` pattern in `runtime_state.py:1116`)
  - `class LifecycleScheduler`:
    - `__init__()`: read `LIFECYCLE_ENABLED`, `LIFECYCLE_CRON_EXPRESSION`
    - `async def start()`: parse cron, schedule periodic runs
    - `async def trigger(force=False)`: manual trigger
    - `async def stop()`: cancel scheduled task

- [ ] **Step 4: Wire into runtime_state.py** — add `lifecycle_scheduler` attribute to runtime state, initialize in startup

- [ ] **Step 5: Add maintenance endpoints** — in `api/maintenance.py`:
  - `POST /lifecycle/trigger` — force-run lifecycle engine
  - `GET /lifecycle/status` — return last run info from `lifecycle_log`

- [ ] **Step 6: Run test, verify PASS**

- [ ] **Step 7: Commit** — `feat: lifecycle scheduler with cron and maintenance API`

---

## Task 10: Query Expansion

**Files:**
- Create: `backend/extraction/query_expansion.py`
- Modify: `backend/mcp_server.py` (search pipeline, ~L4420-4590)
- Create: `backend/tests/test_query_expansion.py`

- [ ] **Step 1: Write test** — `test_query_expansion.py`:
  - `test_short_query_expands_keywords`: mock LLM, query "vim" → returns 4-6 keyword variants
  - `test_long_query_expands_rephrases`: query > 15 chars → up to 3 rephrased variants
  - `test_cjk_adds_english`: Chinese query → prompt includes English keyword hint
  - `test_llm_failure_returns_original`: LLM error → returns only original query
  - `test_disabled_returns_original`: `QUERY_EXPANSION_ENABLED=false` → no expansion
  - `test_multi_hit_boost`: same memory hit by 2 variants → score boosted by `1 + 0.1 * ln(2)`

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Implement `query_expansion.py`**:
  - `_detect_cjk(text) -> bool`: check for CJK unicode ranges
  - `async def expand_query(query: str) -> List[str]`:
    1. Check `QUERY_EXPANSION_ENABLED` (default true), `QUERY_EXPANSION_MIN_QUERY_LEN` (default 2)
    2. If len ≤ 15: prompt LLM for 4-6 synonym keywords, temp=0.2
    3. If len > 15: prompt LLM for up to 3 rephrases, temp=0.4
    4. CJK hint in prompt when detected
    5. LLM call via `ROUTER_API_BASE`, timeout `QUERY_EXPANSION_TIMEOUT_SEC` (3s)
    6. Parse response, return `[original_query] + expanded_variants`
    7. On error → return `[original_query]`
  - `def apply_multi_hit_boost(results_by_variant: List[List[Dict]]) -> List[Dict]`:
    - Count hits per memory_id across variants
    - Apply `score *= (1 + 0.1 * ln(hit_count))` for hit_count > 1
    - Merge and deduplicate by memory_id

- [ ] **Step 4: Wire into search pipeline** — in `mcp_server.py` `search_memory()`, after query preprocessing (~L4420) and before calling sqlite_client search (~L4550):
  - If mode is `hybrid` or `semantic` and `QUERY_EXPANSION_ENABLED`:
    - Call `expand_query(query_effective)`
    - Run search for each variant
    - Apply `apply_multi_hit_boost`
    - Use merged results instead of single-query results

- [ ] **Step 5: Run test, verify PASS**

- [ ] **Step 6: Commit** — `feat: add query expansion with CJK awareness`

---

## Task 11: Integration Test + Env Var Documentation

**Files:**
- Create: `backend/tests/test_integration_lifecycle.py`
- Modify: `.env.example`

- [ ] **Step 1: Write integration test** — `test_integration_lifecycle.py`:
  - Full flow: ingest conversation → fast extracts to core, deep extracts to working → run lifecycle → working promoted → search with feedback → lifecycle adjusts importance
  - Uses real SQLite DB (tmp_path), mocked LLM

- [ ] **Step 2: Run test, verify PASS**

- [ ] **Step 3: Update `.env.example`** — add all new env vars with comments:
  - Extraction section: `EXTRACTION_ENABLED`, `EXTRACTION_FAST_ENABLED`, `EXTRACTION_DEEP_ENABLED`, `EXTRACTION_DEDUP_WINDOW_SEC`, `EXTRACTION_DEEP_TIMEOUT_SEC`
  - Lifecycle section: `LIFECYCLE_ENABLED`, `LIFECYCLE_CRON_EXPRESSION`, `LIFECYCLE_PROMOTE_THRESHOLD`, `LIFECYCLE_ARCHIVE_VITALITY_THRESHOLD`, `LIFECYCLE_ARCHIVE_STALE_DAYS`, `LIFECYCLE_ARCHIVE_RETENTION_DAYS`, `LIFECYCLE_DEDUP_SIMILARITY_THRESHOLD`
  - Query expansion section: `QUERY_EXPANSION_ENABLED`, `QUERY_EXPANSION_TIMEOUT_SEC`, `QUERY_EXPANSION_MIN_QUERY_LEN`

- [ ] **Step 4: Commit** — `feat: integration test and env var documentation`

---

## Task 12: Run Full Test Suite

- [ ] **Step 1: Run all existing tests** to verify no regressions:
  ```bash
  cd ~/Desktop/link-buddy/packages/memory-palace/backend
  python -m pytest tests/ -v --timeout=60
  ```

- [ ] **Step 2: Fix any failures** — new lifecycle columns should be backward compatible (all have defaults), but check for assumptions in existing tests about Memory model attributes

- [ ] **Step 3: Commit fixes if needed** — `fix: resolve test regressions from lifecycle fields`
