from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_pwsh_in_docker_smoke_script_declares_apply_profile_contract() -> None:
    script_text = (
        PROJECT_ROOT / "scripts" / "smoke_apply_profile_ps1_in_docker.sh"
    ).read_text(encoding="utf-8")

    assert "MEMORY_PALACE_PWSH_DOCKER_IMAGE" in script_text
    assert "mcr.microsoft.com/powershell:7.4-ubuntu-22.04" in script_text
    assert "apply_profile.ps1' -Platform linux -Profile b" in script_text
    assert "apply_profile.ps1' -Platform docker -Profile b" in script_text
    assert "DATABASE_URL=sqlite+aiosqlite:////${PROJECT_ROOT#/}/demo.db" in script_text
    assert "grep -Eq '^MCP_API_KEY=.+$'" in script_text
