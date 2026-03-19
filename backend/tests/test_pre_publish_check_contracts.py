from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def test_apply_profile_shell_accepts_crlf_windows_placeholder_lines() -> None:
    script_text = (PROJECT_ROOT / "scripts" / "apply_profile.sh").read_text(
        encoding="utf-8"
    )

    assert r"agent_memory\\.db\r?$" in script_text


def test_apply_profile_shell_generates_docker_api_key_from_crlf_base_template(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    script_path = project_root / "scripts" / "apply_profile.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)

    source_wrapper = (
        PROJECT_ROOT / "scripts" / "apply_profile.sh"
    ).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "")
    with script_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(source_wrapper)
    script_path.chmod(0o755)

    (project_root / ".env.example").write_bytes(b"MCP_API_KEY=\r\n")
    profile_path = project_root / "deploy" / "profiles" / "docker" / "profile-a.env"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_bytes(
        b"SEARCH_DEFAULT_MODE=keyword\r\n"
        b"RETRIEVAL_EMBEDDING_BACKEND=none\r\n"
        b"RETRIEVAL_RERANKER_ENABLED=false\r\n"
    )

    result = subprocess.run(
        ["bash", "scripts/apply_profile.sh", "docker", "a", ".env.generated"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "[auto-fill] MCP_API_KEY generated for docker profile" in result.stdout
    generated_lines = (project_root / ".env.generated").read_text(encoding="utf-8").splitlines()
    mcp_api_key_line = next(line for line in generated_lines if line.startswith("MCP_API_KEY="))
    assert mcp_api_key_line != "MCP_API_KEY="
