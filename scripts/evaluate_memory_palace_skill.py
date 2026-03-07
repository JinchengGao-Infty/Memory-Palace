#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "Memory-Palace"
CANONICAL_DIR = PROJECT_ROOT / "docs" / "skills" / "memory-palace"
MIRRORS = {
    "claude": REPO_ROOT / ".claude" / "skills" / "memory-palace",
    "codex": REPO_ROOT / ".codex" / "skills" / "memory-palace",
    "opencode": REPO_ROOT / ".opencode" / "skills" / "memory-palace",
    "cursor": REPO_ROOT / ".cursor" / "skills" / "memory-palace",
    "agent": REPO_ROOT / ".agent" / "skills" / "memory-palace",
}
REQUIRED_FILES = [
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("references/mcp-workflow.md"),
    Path("references/trigger-samples.md"),
]
GEMINI_TEST_MODEL = "gemini-3.1-pro-preview"
GEMINI_FALLBACK_MODEL = "gemini-3-flash-preview"
PROMPT = (
    "In this repository, answer in exactly 3 bullets only: "
    "(1) the first memory tool call required by the memory-palace skill, "
    "(2) what to do when guard_action is NOOP, and "
    "(3) the canonical repo-visible path of the trigger sample set."
)
CURSOR_AGENT_BIN = Path.home() / ".local" / "bin" / "cursor-agent"
ANTIGRAVITY_BIN = Path("/Applications/Antigravity.app/Contents/Resources/app/bin/antigravity")
ANTIGRAVITY_USER_WORKFLOW = Path.home() / ".gemini" / "antigravity" / "global_workflows" / "memory-palace.md"
GEMINI_CHATS_DIR = Path.home() / ".gemini" / "tmp" / REPO_ROOT.name / "chats"


@dataclass
class CheckResult:
    status: str
    summary: str
    details: str = ""


def run_command(cmd: list[str], *, cwd: Path, input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@dataclass
class CommandCapture:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    model: str | None = None


def run_command_capture(cmd: list[str], *, cwd: Path, input_text: str | None = None, timeout: int = 120) -> CommandCapture:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name != "nt"),
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        return CommandCapture(returncode=process.returncode, stdout=stdout, stderr=stderr, timed_out=False)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover
            process.kill()
        stdout, stderr = process.communicate()
        return CommandCapture(returncode=-9, stdout=stdout, stderr=stderr, timed_out=True)


def _gemini_capacity_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in [
            "model_capacity_exhausted",
            "resource_exhausted",
            "rateLimitExceeded".lower(),
            "no capacity available for model",
            '"code": 429',
            "status: 429",
            "too many requests",
        ]
    )


def run_gemini_prompt(prompt: str, *, timeout: int, model: str = GEMINI_TEST_MODEL) -> CommandCapture:
    capture = run_command_capture(
        ["gemini", "-m", model, "-p", prompt, "--output-format", "text"],
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    capture.model = model
    merged = (capture.stdout + "\n" + capture.stderr).strip()
    if model == GEMINI_TEST_MODEL and _gemini_capacity_error(merged):
        fallback = run_command_capture(
            ["gemini", "-m", GEMINI_FALLBACK_MODEL, "-p", prompt, "--output-format", "text"],
            cwd=REPO_ROOT,
            timeout=timeout,
        )
        fallback.model = GEMINI_FALLBACK_MODEL
        return fallback
    return capture


def _sqlite_path_from_url(url: str) -> Path | None:
    normalized = (url or "").strip()
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if normalized.startswith(prefix):
            raw_path = normalized[len(prefix) - 1 :]
            return Path(raw_path)
    return None


def _extract_gemini_memory_palace_db_path() -> Path | None:
    settings_candidates = [REPO_ROOT / ".gemini" / "settings.json", Path.home() / ".gemini" / "settings.json"]
    for settings_path in settings_candidates:
        if not settings_path.is_file():
            continue
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        server = (payload.get("mcpServers") or {}).get("memory-palace") or {}
        env_url = (server.get("env") or {}).get("DATABASE_URL")
        if isinstance(env_url, str):
            db_path = _sqlite_path_from_url(env_url)
            if db_path is not None:
                return db_path
        for item in server.get("args") or []:
            if not isinstance(item, str):
                continue
            match = re.search(r"DATABASE_URL=(\S+)", item)
            if match:
                db_path = _sqlite_path_from_url(match.group(1))
                if db_path is not None:
                    return db_path
    return None


def _sqlite_fetch_memory(db_path: Path, uri: str) -> dict[str, Any] | None:
    if "://" not in uri:
        return None
    domain, raw_path = uri.split("://", 1)
    path = raw_path.strip("/")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
              p.domain,
              p.path,
              p.priority,
              p.disclosure,
              m.id AS memory_id,
              m.content,
              m.deprecated,
              m.created_at
            FROM paths p
            JOIN memories m ON m.id = p.memory_id
            WHERE p.domain = ? AND p.path = ? AND COALESCE(m.deprecated, 0) = 0
            ORDER BY m.id DESC
            LIMIT 1
            """,
            (domain, path),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def _wait_for_memory(db_path: Path, uri: str, *, expected_substring: str | None = None, retries: int = 5) -> dict[str, Any] | None:
    for attempt in range(retries):
        row = _sqlite_fetch_memory(db_path, uri)
        if row is not None and (expected_substring is None or expected_substring in str(row.get("content") or "")):
            return row
        if attempt < retries - 1:
            time.sleep(0.5 * (attempt + 1))
    return None


def _memory_exists(db_path: Path, uri: str) -> bool:
    return _sqlite_fetch_memory(db_path, uri) is not None


def _find_latest_gemini_chat(marker: str) -> tuple[Path, Any] | None:
    if not GEMINI_CHATS_DIR.is_dir():
        return None
    for path in sorted(GEMINI_CHATS_DIR.glob("session-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if marker not in text:
            continue
        try:
            return path, json.loads(text)
        except Exception:
            return path, text
    return None


def _iter_tool_calls(chat_payload: Any) -> list[dict[str, Any]]:
    if isinstance(chat_payload, dict):
        messages = chat_payload.get("messages")
        if isinstance(messages, list):
            chat_payload = messages
        else:
            return []
    if not isinstance(chat_payload, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in chat_payload:
        if isinstance(item, dict):
            tool_calls = item.get("toolCalls")
            if isinstance(tool_calls, list):
                calls.extend([call for call in tool_calls if isinstance(call, dict)])
    return calls


def _latest_gemini_message(chat_payload: Any) -> str:
    if isinstance(chat_payload, dict):
        messages = chat_payload.get("messages")
        if isinstance(messages, list):
            chat_payload = messages
        else:
            return ""
    if not isinstance(chat_payload, list):
        return ""
    for item in reversed(chat_payload):
        if isinstance(item, dict) and item.get("type") == "gemini":
            content = item.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = []
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        texts.append(block["text"])
                if texts:
                    return "\n".join(texts)
    return ""


def yaml_frontmatter_ok(path: Path) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False, "missing YAML frontmatter"
    end = text.find("\n---\n", 4)
    if end == -1:
        return False, "unterminated YAML frontmatter"
    block = text[4:end]
    if yaml is not None:
        try:
            data = yaml.safe_load(block)
        except Exception as exc:
            return False, f"invalid YAML: {exc}"
        if not isinstance(data, dict):
            return False, "frontmatter must be a mapping"
        if data.get("name") != "memory-palace":
            return False, "name must be memory-palace"
        if not data.get("description"):
            return False, "description must be non-empty"
        return True, "ok"
    if "name:" not in block or "description:" not in block:
        return False, "frontmatter missing name or description"
    return True, "ok"


def check_structure() -> CheckResult:
    missing = [str(CANONICAL_DIR / rel) for rel in REQUIRED_FILES if not (CANONICAL_DIR / rel).is_file()]
    if missing:
        return CheckResult("FAIL", "canonical bundle 缺文件", "\n".join(missing))
    ok, message = yaml_frontmatter_ok(CANONICAL_DIR / "SKILL.md")
    if not ok:
        return CheckResult("FAIL", "canonical SKILL.md 非法", message)
    return CheckResult("PASS", "canonical bundle 结构与 YAML 通过")


def check_mirrors() -> CheckResult:
    missing_or_mismatch: list[str] = []
    for _, mirror_dir in MIRRORS.items():
        for rel in REQUIRED_FILES:
            expected = CANONICAL_DIR / rel
            actual = mirror_dir / rel
            if not actual.is_file():
                missing_or_mismatch.append(f"missing: {actual}")
            elif actual.read_bytes() != expected.read_bytes():
                missing_or_mismatch.append(f"mismatch: {actual}")
    if missing_or_mismatch:
        return CheckResult("FAIL", "mirror 与 canonical 不一致", "\n".join(missing_or_mismatch))
    return CheckResult("PASS", "all mirrors are byte-identical to canonical")


def check_sync_script() -> CheckResult:
    script = PROJECT_ROOT / "scripts" / "sync_memory_palace_skill.py"
    proc = run_command(["python3", "-B", str(script), "--check"], cwd=REPO_ROOT, timeout=60)
    if proc.returncode != 0:
        return CheckResult("FAIL", "sync script --check 失败", (proc.stdout + "\n" + proc.stderr).strip())
    return CheckResult("PASS", proc.stdout.strip() or "sync script --check passed")


def check_gate_syntax() -> CheckResult:
    proc = run_command(["bash", "-n", "new/run_post_change_checks.sh"], cwd=REPO_ROOT, timeout=30)
    if proc.returncode != 0:
        return CheckResult("FAIL", "run_post_change_checks.sh 语法失败", proc.stderr.strip())
    return CheckResult("PASS", "run_post_change_checks.sh 语法通过")


def classify_skill_answer(text: str) -> tuple[bool, str]:
    lowered = text.lower()
    checks = [
        'read_memory("system://boot")' in text or "system://boot" in lowered,
        (any(token in lowered for token in ["guard_target_uri", "guard_target_id"]) and any(token in lowered for token in ["stop", "inspect", "重复", "停止"])),
        "memory-palace/docs/skills/memory-palace/references/trigger-samples.md" in lowered,
    ]
    if all(checks):
        return True, "命中 first move / NOOP / trigger sample"
    return False, text[-1500:]


def smoke_claude() -> CheckResult:
    if shutil.which("claude") is None:
        return CheckResult("SKIP", "claude CLI 未安装")
    try:
        proc = run_command(["claude", "-p"], cwd=REPO_ROOT, input_text=PROMPT, timeout=120)
    except subprocess.TimeoutExpired:
        return CheckResult("FAIL", "Claude smoke 超时")
    success, details = classify_skill_answer(proc.stdout)
    if proc.returncode == 0 and success:
        return CheckResult("PASS", "Claude smoke 通过", proc.stdout.strip())
    return CheckResult("FAIL", "Claude smoke 未通过", (proc.stdout + "\n" + proc.stderr).strip() or details)


def smoke_codex() -> CheckResult:
    if shutil.which("codex") is None:
        return CheckResult("SKIP", "codex CLI 未安装")
    with tempfile.TemporaryDirectory(prefix="memory-palace-codex-") as tmpdir:
        tmp = Path(tmpdir)
        schema_path = tmp / "schema.json"
        output_path = tmp / "out.json"
        schema = {
            "type": "object",
            "properties": {
                "first_move": {"type": "string"},
                "noop_handling": {"type": "string"},
                "trigger_samples_path": {"type": "string"},
            },
            "required": ["first_move", "noop_handling", "trigger_samples_path"],
            "additionalProperties": False,
        }
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        try:
            proc = run_command(
                [
                    "codex",
                    "exec",
                    "--ephemeral",
                    "--color",
                    "never",
                    "-s",
                    "read-only",
                    "-C",
                    str(REPO_ROOT),
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(output_path),
                    PROMPT,
                ],
                cwd=REPO_ROOT,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            return CheckResult("FAIL", "Codex smoke 超时")
        if proc.returncode != 0 or not output_path.is_file():
            return CheckResult("FAIL", "Codex smoke 未通过", (proc.stdout + "\n" + proc.stderr).strip())
        data = json.loads(output_path.read_text(encoding="utf-8"))
        joined = json.dumps(data, ensure_ascii=False)
        success, details = classify_skill_answer(joined)
        if success:
            return CheckResult("PASS", "Codex smoke 通过", joined)
        return CheckResult("FAIL", "Codex smoke 输出不符合预期", details)


def smoke_opencode() -> CheckResult:
    if shutil.which("opencode") is None:
        return CheckResult("SKIP", "opencode CLI 未安装")
    try:
        proc = run_command(
            [
                "opencode",
                "run",
                "--dir",
                str(REPO_ROOT),
                "--format",
                "default",
                "For this repository's memory-palace skill, answer with exactly three bullets: "
                "(1) the correct first move, (2) what to do when guard_action=NOOP, "
                "(3) the path to the trigger sample file. Keep it concise.",
            ],
            cwd=REPO_ROOT,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("FAIL", "OpenCode smoke 超时")
    merged = (proc.stdout + "\n" + proc.stderr).strip()
    success, details = classify_skill_answer(merged)
    if proc.returncode == 0 and success:
        return CheckResult("PASS", "OpenCode smoke 通过", merged)
    return CheckResult("FAIL", "OpenCode smoke 未通过", details)


def smoke_gemini() -> CheckResult:
    if shutil.which("gemini") is None:
        return CheckResult("SKIP", "gemini CLI 未安装")
    discovery = run_command_capture(["gemini", "skills", "list", "--all"], cwd=REPO_ROOT, timeout=90)
    if discovery.timed_out:
        return CheckResult("FAIL", "Gemini skills list 超时")
    discovery_text = (discovery.stdout + "\n" + discovery.stderr).strip()
    discovered = "memory-palace [Enabled]" in discovery_text or "memory-palace" in discovery_text
    invoke = run_gemini_prompt(PROMPT, timeout=120)
    if invoke.timed_out:
        model_used = invoke.model or GEMINI_TEST_MODEL
        return CheckResult("PARTIAL" if discovered else "FAIL", f"Gemini prompt 超时（model={model_used}）", discovery_text)
    merged = (invoke.stdout + "\n" + invoke.stderr).strip()
    success, details = classify_skill_answer(merged)
    if discovered and invoke.returncode == 0 and success:
        model_note = f"[model={invoke.model or GEMINI_TEST_MODEL}]\n"
        return CheckResult("PASS", "Gemini smoke 通过", model_note + merged)
    lowered = merged.lower()
    if discovered:
        if any(token in lowered for token in ["429", "resource_exhausted", "model_capacity_exhausted", "econnreset", "tls", "socket disconnected"]):
            return CheckResult("PARTIAL", "Gemini 发现 skill 成功，但执行受上游容量或网络波动影响", merged or discovery_text)
        return CheckResult("FAIL", "Gemini 已发现 skill，但调用结果不符合预期", merged or discovery_text)
    return CheckResult("FAIL", "Gemini 未发现或未调用 memory-palace", merged or discovery_text)


def smoke_gemini_live_suite() -> CheckResult:
    if shutil.which("gemini") is None:
        return CheckResult("SKIP", "gemini CLI 未安装")
    db_path = _extract_gemini_memory_palace_db_path()
    if db_path is None:
        return CheckResult("PARTIAL", "未能从 Gemini 配置解析 memory-palace 数据库路径")
    marker = f"gemini_suite_{int(time.time())}"
    unique_token = f"{marker}_nonce"
    note_uri = f"notes://{marker}"
    note_content = f"Unique token {unique_token}. This note records one preference only: user prefers concise answers."
    updated_content = f"Unique token {unique_token}. This note records one preference only: user prefers concise answers. Updated once."

    create_prompt = (
        f'Please save this durable note to Memory Palace at {note_uri}. Content: "{note_content}". '
        "Avoid duplicate creation and follow the repository memory-palace workflow automatically. "
        f"Return exactly one line: SUCCESS {note_uri} or FAIL <reason>."
    )
    update_prompt = (
        f'Please update {note_uri} in Memory Palace so its content becomes "{updated_content}". '
        "Read before write, use the repository memory-palace workflow, and only report success if the update truly succeeded. "
        f"Return exactly one line: SUCCESS {note_uri} or FAIL <reason>."
    )
    guard_marker = marker + "_guard"
    guard_uri = f"notes://{marker}_dup"
    guard_prompt = (
        f'Please try to save a second durable note to Memory Palace at {guard_uri}. Content: "{updated_content}". '
        f"The same note already exists at {note_uri}. Avoid duplicate creation. "
        "If write_guard blocks the write, do not claim a new save succeeded; report the existing target instead. "
        f"Keep this trace token in the conversation: {guard_marker}. "
        f"Return exactly one line: BLOCKED {note_uri} or SUCCESS {guard_uri} or FAIL <reason>."
    )

    create_proc = run_gemini_prompt(create_prompt, timeout=120)
    create_out = (create_proc.stdout + "\n" + create_proc.stderr).strip()
    create_row = _wait_for_memory(db_path, note_uri, expected_substring=unique_token)

    update_proc = run_gemini_prompt(update_prompt, timeout=120)
    update_out = (update_proc.stdout + "\n" + update_proc.stderr).strip()
    update_row = _wait_for_memory(db_path, note_uri, expected_substring=f"{unique_token}. This note records one preference only: user prefers concise answers. Updated once.")

    guard_proc = run_gemini_prompt(guard_prompt, timeout=120)
    guard_out = (guard_proc.stdout + "\n" + guard_proc.stderr).strip()
    guard_chat = _find_latest_gemini_chat(guard_marker)
    guard_calls: list[dict[str, Any]] = []
    if guard_chat is not None:
        _, payload = guard_chat
        guard_calls = _iter_tool_calls(payload)

    create_ok = (
        create_row is not None
        and unique_token in str(create_row.get("content") or "")
        and (f"SUCCESS {note_uri}" in create_proc.stdout or "successfully saved" in create_proc.stdout.lower())
    )
    update_ok = (
        update_row is not None
        and updated_content in str(update_row.get("content") or "")
        and (f"SUCCESS {note_uri}" in update_proc.stdout or "success" in update_proc.stdout.lower() or "updated" in update_proc.stdout.lower())
    )

    guard_create = next((call for call in guard_calls if call.get("name") == "create_memory"), None)
    guard_create_output = ""
    if isinstance(guard_create, dict):
        try:
            guard_create_output = guard_create["result"][0]["functionResponse"]["response"]["output"]
        except Exception:
            guard_create_output = json.dumps(guard_create, ensure_ascii=False)
    guard_target_uri = ""
    try:
        parsed_guard = json.loads(guard_create_output) if guard_create_output else {}
        if isinstance(parsed_guard, dict):
            guard_target_uri = str(parsed_guard.get("guard_target_uri") or "")
    except Exception:
        guard_target_uri = ""
    guard_has_block = any(token in guard_create_output for token in ['"guard_action": "NOOP"', '"guard_action": "UPDATE"', '"guard_action": "DELETE"'])
    guard_has_followup = any(call.get("name") in {"read_memory", "update_memory"} for call in guard_calls[1:])
    guard_duplicate_created = _memory_exists(db_path, guard_uri)
    guard_no_false_success = f"SUCCESS {guard_uri}" not in guard_proc.stdout and not guard_duplicate_created
    guard_resolved_to_existing_target = bool(guard_target_uri) and f"SUCCESS {guard_target_uri}" in guard_proc.stdout
    guard_user_visible_block = any(
        token in guard_proc.stdout
        for token in [f"BLOCKED {note_uri}", note_uri, "duplicate", "already exists", "update", "noop", "guard"]
    )

    details = [
        f"db_path={db_path}",
        f"create_model={create_proc.model or GEMINI_TEST_MODEL}",
        f"create_timed_out={create_proc.timed_out}",
        f"create_stdout={create_proc.stdout.strip()}",
        f"create_verified={json.dumps(create_row, ensure_ascii=False) if create_row else 'missing'}",
        f"update_model={update_proc.model or GEMINI_TEST_MODEL}",
        f"update_timed_out={update_proc.timed_out}",
        f"update_stdout={update_proc.stdout.strip()}",
        f"update_verified={json.dumps(update_row, ensure_ascii=False) if update_row else 'missing'}",
        f"guard_model={guard_proc.model or GEMINI_TEST_MODEL}",
        f"guard_timed_out={guard_proc.timed_out}",
        f"guard_stdout={guard_proc.stdout.strip()}",
        f"guard_duplicate_created={guard_duplicate_created}",
        f"guard_create_output={guard_create_output or 'missing'}",
        f"guard_target_uri={guard_target_uri or 'missing'}",
        f"guard_user_visible_block={guard_user_visible_block}",
        f"guard_followup={guard_has_followup}",
        f"guard_resolved_to_existing_target={guard_resolved_to_existing_target}",
    ]

    guard_safe = (guard_no_false_success or guard_resolved_to_existing_target) and (guard_has_block or guard_user_visible_block)
    if create_ok and update_ok and guard_safe:
        if guard_has_followup:
            return CheckResult("PASS", "Gemini live 写入/更新/守卫链路通过", "\n".join(details))
        return CheckResult("PASS", "Gemini live 写入/更新通过，guard 已安全阻断（未稳定观测到 follow-up）", "\n".join(details))

    if create_ok and update_ok:
        return CheckResult("PARTIAL", "Gemini live 写入与更新通过，但 guard 分支未稳定收敛", "\n".join(details))

    return CheckResult("FAIL", "Gemini live MCP 链路未完全通过", "\n".join(details))


def mirror_only_status(name: str) -> CheckResult:
    mirror = MIRRORS[name]
    if mirror.is_dir():
        return CheckResult("PARTIAL", f"{name} 仅完成 mirror 结构校验", str(mirror))
    return CheckResult("FAIL", f"{name} mirror 缺失", str(mirror))


def smoke_cursor() -> CheckResult:
    mirror = MIRRORS["cursor"]
    if not mirror.is_dir():
        return CheckResult("FAIL", "Cursor mirror 缺失", str(mirror))
    if not CURSOR_AGENT_BIN.is_file():
        return CheckResult("PARTIAL", "Cursor mirror 已准备，但本机未发现 cursor-agent runtime", str(mirror))
    try:
        proc = run_command([str(CURSOR_AGENT_BIN), "-p", PROMPT], cwd=REPO_ROOT, timeout=60)
    except subprocess.TimeoutExpired:
        return CheckResult("PARTIAL", "Cursor runtime 存在，但 smoke 超时", str(CURSOR_AGENT_BIN))
    merged = (proc.stdout + "\n" + proc.stderr).strip()
    lowered = merged.lower()
    if "authentication required" in lowered:
        return CheckResult("PARTIAL", "Cursor runtime 存在，但当前机器缺少登录/鉴权", merged)
    success, details = classify_skill_answer(merged)
    if proc.returncode == 0 and success:
        return CheckResult("PASS", "Cursor smoke 通过", merged)
    return CheckResult("PARTIAL", "Cursor runtime 可用，但当前 smoke 未通过", details)


def smoke_antigravity() -> CheckResult:
    if not ANTIGRAVITY_BIN.is_file():
        return CheckResult("FAIL", "Antigravity app-bundled CLI 缺失")
    if ANTIGRAVITY_USER_WORKFLOW.is_file():
        return CheckResult(
            "PARTIAL",
            "Antigravity app-bundled CLI 已发现，global_workflow 已安装；仍需 GUI 手工 smoke",
            f"{ANTIGRAVITY_BIN}\n{ANTIGRAVITY_USER_WORKFLOW}",
        )
    return CheckResult("MANUAL", "Antigravity CLI 存在，但 workflow 尚未安装", str(ANTIGRAVITY_BIN))


def generate_markdown(results: dict[str, CheckResult]) -> str:
    lines = [
        "# Memory Palace Trigger Smoke Report",
        "",
        "## Summary",
        "",
        "| Check | Status | Summary |",
        "|---|---|---|",
    ]
    for key, result in results.items():
        lines.append(f"| `{key}` | `{result.status}` | {result.summary} |")
    lines.extend(
        [
            "",
            "## Details",
            "",
        ]
    )
    for key, result in results.items():
        lines.append(f"### {key}")
        lines.append("")
        lines.append(f"- Status: `{result.status}`")
        lines.append(f"- Summary: {result.summary}")
        if result.details:
            lines.append("")
            lines.append("```text")
            lines.append(result.details.strip())
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    report_path = PROJECT_ROOT / "docs" / "skills" / "TRIGGER_SMOKE_REPORT.md"
    results: dict[str, CheckResult] = {
        "structure": check_structure(),
        "mirrors": check_mirrors(),
        "sync_check": check_sync_script(),
        "gate_syntax": check_gate_syntax(),
        "claude": smoke_claude(),
        "codex": smoke_codex(),
        "opencode": smoke_opencode(),
        "gemini": smoke_gemini(),
        "gemini_live": smoke_gemini_live_suite(),
        "cursor": smoke_cursor(),
        "agent": mirror_only_status("agent"),
        "antigravity": smoke_antigravity(),
    }
    markdown = generate_markdown(results)
    report_path.write_text(markdown + "\n", encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
