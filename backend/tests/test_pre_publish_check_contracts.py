from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write_shell_script(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content.replace("\r\n", "\n").replace("\r", ""))
    path.chmod(0o755)


def _write_windows_cmd(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(content.replace("\r\n", "\n").replace("\r", ""))


def _run_command(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )


def test_pre_publish_check_uses_cross_platform_python_scans_and_env_globs() -> None:
    script_text = (PROJECT_ROOT / "scripts" / "pre_publish_check.sh").read_text(
        encoding="utf-8"
    )

    assert 'resolve_python_cmd()' in script_text
    assert 'resolve_python_project_root()' in script_text
    assert 'build_personal_path_scan_regex()' in script_text
    assert '".env.*"' in script_text
    assert '".playwright-cli"' in script_text
    assert 'python3 python' in script_text
    assert 'C:/Users/' in script_text
    assert 'cygpath -w "${PROJECT_ROOT}"' in script_text
    assert '"/windowsapps/"' in script_text
    assert 'MSYS2_ARG_CONV_EXCL="*"' in script_text
    assert 'xargs -0 rg -l -n --no-messages' not in script_text
    assert "rg -n '^[A-Z0-9_]*API_KEY=.+$' .env.example" not in script_text
    assert '".pytest_cache"' in script_text
    assert 'git ls-files --others --exclude-standard' in script_text


def test_apply_profile_shell_accepts_crlf_windows_placeholder_lines() -> None:
    script_text = (PROJECT_ROOT / "scripts" / "apply_profile.sh").read_text(
        encoding="utf-8"
    )

    assert r"agent_memory\.db([[:space:]]+#.*)?[[:space:]]*\r?$" in script_text
    assert "macos|linux|windows|docker" in script_text


def test_apply_profile_shell_generates_docker_api_key_from_crlf_base_template(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    script_path = project_root / "scripts" / "apply_profile.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)

    source_wrapper = (
        "openssl() { return 1; }\n"
        "python3() { return 1; }\n"
        "python() {\n"
        "  printf 'python-fallback-token\\n'\n"
        "}\n"
        + (
            PROJECT_ROOT / "scripts" / "apply_profile.sh"
        ).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "")
    )
    _write_shell_script(script_path, source_wrapper)

    (project_root / ".env.example").write_bytes(b"MCP_API_KEY=\r\n")
    profile_path = project_root / "deploy" / "profiles" / "docker" / "profile-a.env"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_bytes(
        b"SEARCH_DEFAULT_MODE=keyword\r\n"
        b"RETRIEVAL_EMBEDDING_BACKEND=none\r\n"
        b"RETRIEVAL_RERANKER_ENABLED=false\r\n"
    )

    result = _run_command(
        ["bash", "scripts/apply_profile.sh", "docker", "a", ".env.generated"],
        cwd=project_root,
    )

    assert result.returncode == 0
    assert "[auto-fill] MCP_API_KEY generated for docker profile" in result.stdout
    generated_lines = (project_root / ".env.generated").read_text(encoding="utf-8").splitlines()
    mcp_api_key_line = next(line for line in generated_lines if line.startswith("MCP_API_KEY="))
    assert mcp_api_key_line != "MCP_API_KEY="


def test_apply_profile_shell_accepts_linux_platform_with_dedicated_profile_template(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    script_path = project_root / "scripts" / "apply_profile.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)

    source_wrapper = (
        "openssl() { return 1; }\n"
        "python3() { return 1; }\n"
        "python() {\n"
        "  printf 'python-fallback-token\\n'\n"
        "}\n"
        + (
            PROJECT_ROOT / "scripts" / "apply_profile.sh"
        ).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "")
    )
    _write_shell_script(script_path, source_wrapper)

    (project_root / ".env.example").write_bytes(
        b"DATABASE_URL=sqlite+aiosqlite:////Users/<your-user>/memory_palace/agent_memory.db\r\n"
    )
    profile_path = project_root / "deploy" / "profiles" / "linux" / "profile-b.env"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_bytes(
        b"PROFILE_MARKER=linux_b\r\n"
        b"SEARCH_DEFAULT_MODE=keyword\r\n"
        b"RETRIEVAL_EMBEDDING_BACKEND=hash\r\n"
    )

    result = _run_command(
        ["bash", "scripts/apply_profile.sh", "linux", "b", ".env.generated"],
        cwd=project_root,
    )

    assert result.returncode == 0
    assert "Generated" in result.stdout
    generated_lines = (project_root / ".env.generated").read_text(encoding="utf-8").splitlines()
    assert "PROFILE_MARKER=linux_b" in generated_lines
    database_url_line = next(
        line for line in generated_lines if line.startswith("DATABASE_URL=")
    )
    assert "<your-user>" not in database_url_line
    assert database_url_line.startswith("DATABASE_URL=sqlite+aiosqlite:////")
    assert database_url_line.endswith("demo.db")


def test_linux_profile_templates_exist_with_home_placeholders() -> None:
    for relative_path in (
        "deploy/profiles/linux/profile-a.env",
        "deploy/profiles/linux/profile-b.env",
        "deploy/profiles/linux/profile-c.env",
        "deploy/profiles/linux/profile-d.env",
    ):
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "DATABASE_URL=sqlite+aiosqlite:////home/<your-user>/memory_palace/agent_memory.db" in text


def test_apply_profile_shell_falls_back_to_python_when_openssl_is_unusable(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    script_path = project_root / "scripts" / "apply_profile.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)

    source_wrapper = (
        "openssl() { return 1; }\n"
        "python3() { return 1; }\n"
        "python() {\n"
        "  printf 'python-fallback-token\\n'\n"
        "}\n"
        + (
            PROJECT_ROOT / "scripts" / "apply_profile.sh"
        ).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "")
    )
    _write_shell_script(script_path, source_wrapper)

    (project_root / ".env.example").write_text("MCP_API_KEY=\n", encoding="utf-8")
    profile_path = project_root / "deploy" / "profiles" / "docker" / "profile-a.env"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        "SEARCH_DEFAULT_MODE=keyword\n"
        "RETRIEVAL_EMBEDDING_BACKEND=none\n"
        "RETRIEVAL_RERANKER_ENABLED=false\n",
        encoding="utf-8",
    )

    result = _run_command(
        ["bash", "scripts/apply_profile.sh", "docker", "a", ".env.generated"],
        cwd=project_root,
    )

    assert result.returncode == 0, result.stderr
    generated_lines = (project_root / ".env.generated").read_text(encoding="utf-8").splitlines()
    mcp_api_key_line = next(line for line in generated_lines if line.startswith("MCP_API_KEY="))
    assert mcp_api_key_line == "MCP_API_KEY=python-fallback-token"


def test_repo_ignore_rules_cover_local_review_reports_and_local_scan_artifacts() -> None:
    gitignore_text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore_text = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "code_review_report.md" in gitignore_text
    assert "security_best_practices_report.md" in gitignore_text
    assert ".tmp_tracked_files.txt" in gitignore_text

    for expected in (
        ".codex/",
        ".cursor/",
        ".opencode/",
        ".gemini/",
        ".agent/",
        ".mcp.json",
        ".mcp.json.bak",
        ".playwright-cli/",
        ".tmp/",
        ".pytest_cache/",
        "**/__pycache__/",
        "frontend/dist/",
    ):
        assert expected in dockerignore_text
